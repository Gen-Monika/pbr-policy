import re,sys
t=open(sys.argv[1]).read()
blocks=re.split(r'\*\*\* Timestep (\d+):',t)
rb=[int(blocks[i]) for i in range(1,len(blocks),2) if 'Rebuilding Stokes' in blocks[i+1]]
print('n',len(rb),'n<100',sum(1 for x in rb if x<100),'post',[x for x in rb if x>=100])
