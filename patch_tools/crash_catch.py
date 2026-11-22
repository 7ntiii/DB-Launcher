"""Attach to the next lichii.exe that starts and print where it crashes (an unhandled exception),
symbolised with its .pdb (dbghelp). First-chance exceptions (fastmem faults, C++ throws) pass on.
Usage: python tools/crash_catch.py [process name] [timeout seconds]
Start the game (tools/auto/run_game.py) right after this starts waiting."""
import ctypes
import ctypes.wintypes as wt
import struct
import sys
import time

k32 = ctypes.WinDLL('kernel32', use_last_error=True)
dbghelp = ctypes.WinDLL('dbghelp', use_last_error=True)
dbghelp.SymGetModuleBase64.restype = ctypes.c_uint64
dbghelp.SymGetModuleBase64.argtypes = [wt.HANDLE, ctypes.c_uint64]
NAME = (sys.argv[1] if len(sys.argv) > 1 else 'lichii.exe').lower()
TIMEOUT = float(sys.argv[2]) if len(sys.argv) > 2 else 300


class PROCESSENTRY32W(ctypes.Structure):
    _fields_ = [('dwSize', wt.DWORD), ('cntUsage', wt.DWORD), ('th32ProcessID', wt.DWORD),
                ('th32DefaultHeapID', ctypes.c_void_p), ('th32ModuleID', wt.DWORD),
                ('cntThreads', wt.DWORD), ('th32ParentProcessID', wt.DWORD),
                ('pcPriClassBase', ctypes.c_long), ('dwFlags', wt.DWORD),
                ('szExeFile', ctypes.c_wchar * 260)]


def find_pid():
    snap = k32.CreateToolhelp32Snapshot(2, 0)
    entry = PROCESSENTRY32W()
    entry.dwSize = ctypes.sizeof(entry)
    ok = k32.Process32FirstW(snap, ctypes.byref(entry))
    pid = None
    while ok:
        if entry.szExeFile.lower() == NAME:
            pid = entry.th32ProcessID
        ok = k32.Process32NextW(snap, ctypes.byref(entry))
    k32.CloseHandle(snap)
    return pid


class DEBUG_EVENT(ctypes.Structure):
    _fields_ = [('dwDebugEventCode', wt.DWORD), ('dwProcessId', wt.DWORD),
                ('dwThreadId', wt.DWORD), ('pad', wt.DWORD), ('u', ctypes.c_byte * 160)]


class SYMBOL_INFO(ctypes.Structure):
    _fields_ = [('SizeOfStruct', wt.ULONG), ('TypeIndex', wt.ULONG), ('Reserved', ctypes.c_uint64 * 2),
                ('Index', wt.ULONG), ('Size', wt.ULONG), ('ModBase', ctypes.c_uint64),
                ('Flags', wt.ULONG), ('Value', ctypes.c_uint64), ('Address', ctypes.c_uint64),
                ('Register', wt.ULONG), ('Scope', wt.ULONG), ('Tag', wt.ULONG),
                ('NameLen', wt.ULONG), ('MaxNameLen', wt.ULONG), ('Name', ctypes.c_char * 512)]


class IMAGEHLP_LINE64(ctypes.Structure):
    _fields_ = [('SizeOfStruct', wt.DWORD), ('Key', ctypes.c_void_p), ('LineNumber', wt.DWORD),
                ('FileName', ctypes.c_char_p), ('Address', ctypes.c_uint64)]


psapi = ctypes.WinDLL('psapi')


class MODULEINFO(ctypes.Structure):
    _fields_ = [('base', ctypes.c_void_p), ('size', wt.DWORD), ('entry', ctypes.c_void_p)]


def module_of(process, address):
    mods = (ctypes.c_void_p * 2048)()
    needed = wt.DWORD()
    psapi.EnumProcessModulesEx(process, mods, ctypes.sizeof(mods), ctypes.byref(needed), 3)
    base = 0
    for m in mods[: needed.value // 8]:
        info = MODULEINFO()
        if m and psapi.GetModuleInformation(process, ctypes.c_void_p(m), ctypes.byref(info), ctypes.sizeof(info)):
            if info.base <= address < info.base + info.size:
                base = info.base
    if not base:
        return '?'
    name = ctypes.create_unicode_buffer(260)
    psapi.GetModuleFileNameExW(process, ctypes.c_void_p(base), name, 260)
    return f'{name.value.split(chr(92))[-1]}+{address - base:#x}'


def symbol(process, address):
    info = SYMBOL_INFO()
    info.SizeOfStruct = ctypes.sizeof(SYMBOL_INFO) - 512 + 1
    info.MaxNameLen = 511
    disp = ctypes.c_uint64()
    text = f'{address:#x}'
    if dbghelp.SymFromAddr(process, ctypes.c_uint64(address), ctypes.byref(disp), ctypes.byref(info)):
        text += f' {info.Name.decode(errors="replace")}+{disp.value:#x}'
        line = IMAGEHLP_LINE64()
        line.SizeOfStruct = ctypes.sizeof(IMAGEHLP_LINE64)
        d32 = wt.DWORD()
        if dbghelp.SymGetLineFromAddr64(process, ctypes.c_uint64(address), ctypes.byref(d32), ctypes.byref(line)):
            text += f'  ({line.FileName.decode(errors="replace")}:{line.LineNumber})'
        return text, True
    return text, False


def main():
    end = time.time() + TIMEOUT
    pid = None
    while time.time() < end and not pid:
        pid = find_pid()
        if not pid:
            time.sleep(0.02)
    if not pid:
        sys.exit('no process')
    if not k32.DebugActiveProcess(pid):
        sys.exit(f'attach failed {ctypes.get_last_error()}')
    k32.DebugSetProcessKillOnExit(False)
    print('attached', pid, flush=True)
    process = k32.OpenProcess(0x1F0FFF, False, pid)
    dbghelp.SymSetOptions(0x2 | 0x10 | 0x200)  # deferred loads, line numbers, fail-critical off
    dbghelp.SymInitialize(process, None, True)
    event = DEBUG_EVENT()
    k32.WaitForDebugEvent.argtypes = [ctypes.POINTER(DEBUG_EVENT), wt.DWORD]
    while True:
        if not k32.WaitForDebugEvent(ctypes.byref(event), 1000):
            continue
        status = 0x00010002  # DBG_CONTINUE
        code = event.dwDebugEventCode
        if code == 1:  # exception
            raw = bytes(event.u)
            exc_code, flags = struct.unpack_from('<II', raw, 0)
            address = struct.unpack_from('<Q', raw, 16)[0]
            nparams = struct.unpack_from('<I', raw, 24)[0]
            params = struct.unpack_from('<2Q', raw, 32) if nparams >= 2 else (0, 0)
            first_chance = struct.unpack_from('<I', raw, 152)[0]
            if exc_code in (0x80000003, 0x4000001F) and first_chance:
                pass  # the attach breakpoint
            elif first_chance:
                status = 0x80010001  # DBG_EXCEPTION_NOT_HANDLED
                if exc_code == 0xC0000005:
                    dbghelp.SymRefreshModuleList(process)
                    text, known = symbol(process, address)
                    if known:
                        print(f'first-chance AV at {text} access={params}', flush=True)
            else:
                dbghelp.SymRefreshModuleList(process)
                print(f'UNHANDLED {exc_code:#x} at {symbol(process, address)[0]} [{module_of(process, address)}] access={params}', flush=True)
                thread = k32.OpenThread(0x1FFFFF, False, event.dwThreadId)
                raw_ctx = ctypes.create_string_buffer(1232 + 16)
                base = ctypes.addressof(raw_ctx)
                base += (16 - base % 16) % 16
                ctypes.memmove(base + 0x30, struct.pack('<I', 0x10000B), 4)  # CONTEXT_FULL (AMD64)
                k32.OpenProcess.restype = wt.HANDLE
                if not k32.GetThreadContext(wt.HANDLE(thread), ctypes.c_void_p(base)):
                    print('GetThreadContext failed', ctypes.get_last_error(), flush=True)
                else:
                    rsp = ctypes.c_uint64.from_address(base + 0x98).value
                    stack = (ctypes.c_uint64 * 4096)()
                    read = ctypes.c_size_t()
                    k32.ReadProcessMemory(process, ctypes.c_void_p(rsp), stack, ctypes.sizeof(stack), ctypes.byref(read))
                    shown = 0
                    for value in stack[: read.value // 8]:
                        if value < 0x10000:
                            continue
                        mod = module_of(process, value)
                        if mod != '?' and shown < 60:
                            print('  ', symbol(process, value)[0], mod, flush=True)
                            shown += 1
                k32.TerminateProcess(process, 1)
                return
        elif code == 5:  # process exit
            print('process exited', flush=True)
            return
        k32.ContinueDebugEvent(event.dwProcessId, event.dwThreadId, status)


main()
