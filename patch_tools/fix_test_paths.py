import glob,os
d=os.path.join(os.path.dirname(os.path.abspath(__file__)),'..','tests','v30-tests')
R=[(r'%~dp0..\Eglantine-Duskbloods-v30\Eglantine-Duskbloods-v30', r'%~dp0..\..\emulators\v30-eglantine'),
   (r'%~dp0..\diag\shaders', r'%~dp0..\..\diag\v30-shader-dump')]
for f in glob.glob(os.path.join(d,'*.cmd')):
    t=open(f,newline='').read(); o=t
    for a,b in R: t=t.replace(a,b)
    if t!=o: open(f,'w',newline='').write(t); print('fixed',os.path.basename(f))
