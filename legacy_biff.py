"""Minimal read-only XLS/BIFF8 reader using only Python standard library, for audit of legacy formulas and cached values.
Not a generalized workbook writer. Retains formulas as cached values if present.
"""
import struct, math
from collections import defaultdict
U16=lambda b,o=0:struct.unpack_from('<H',b,o)[0]
U32=lambda b,o=0:struct.unpack_from('<I',b,o)[0]
U64=lambda b,o=0:struct.unpack_from('<Q',b,o)[0]
class OLE:
 def __init__(self,path):
  self.b=open(path,'rb').read()
  assert self.b[:8]==bytes.fromhex('D0CF11E0A1B11AE1')
  self.ss=1<<U16(self.b,30)
  difat=[U32(self.b,76+i*4) for i in range(109)];nf=U32(self.b,44);next_difat=U32(self.b,68);nd=U32(self.b,72)
  for _ in range(nd):
   sec=self.sec(next_difat)
   difat.extend(U32(sec,i*4) for i in range(self.ss//4-1))
   next_difat=U32(sec,self.ss-4)
  difat=[x for x in difat if x<0xFFFFFFFA][:nf]
  self.fat=[]
  for idx in difat:self.fat.extend(struct.unpack('<%dI'%(self.ss//4),self.sec(idx)))
  d=self.chain(U32(self.b,48))
  self.entries=[]
  for p in range(0,len(d),128):
   r=d[p:p+128]
   if len(r)<128:continue
   size=U16(r,64);name=r[:size-2].decode('utf-16le',errors='replace') if size>=2 else ''
   self.entries.append((name,r[66],U32(r,116),U64(r,120)))
  self.cutoff=U32(self.b,56)
  self.mini_fat=[]
  fm=U32(self.b,60)
  if fm<0xfffffffa:
   for sec in self.chain(fm):pass
   dat=self.chain(fm)
   self.mini_fat=list(struct.unpack('<%dI'%(len(dat)//4),dat))
  rt=self.entries[0]
  self.mini_stream=self.chain(rt[2])[:rt[3]]
 def sec(self,n):return self.b[(n+1)*self.ss:(n+2)*self.ss]
 def chain(self,first):
  bs=[];x=first;seen=set()
  while x<0xFFFFFFFA and x not in seen and x<len(self.fat):
   seen.add(x);bs.append(self.sec(x));x=self.fat[x]
  return b''.join(bs)
 def open(self,name):
  ent=next((x for x in self.entries if x[0]==name),None)
  if ent is None:raise KeyError((name,self.entries))
  n,t,first,size=ent
  if size>=self.cutoff:return self.chain(first)[:size]
  bs=[];cur=first;seen=set()
  while cur<0xFFFFFFFA and cur not in seen and cur<len(self.mini_fat):
   seen.add(cur);bs.append(self.mini_stream[cur*64:(cur+1)*64]);cur=self.mini_fat[cur]
  return b''.join(bs)[:size]
def records(buffer,offset=0,limit=None):
 k=offset;end=min(limit or len(buffer),len(buffer))
 while k+4<=end:
  code,length=struct.unpack_from('<HH',buffer,k)
  if k+4+length>end:break
  yield k,code,buffer[k+4:k+4+length]
  k+=4+length

def parse_xl_unicode(data,pos=0,shortlen=False):
 if shortlen:
  if pos>=len(data):return '',pos
  n=data[pos];pos+=1
 else:
  if pos+2>len(data):return '',pos
  n=U16(data,pos);pos+=2
 if pos>=len(data):return '',pos
 flag=data[pos];pos+=1
 rich=U16(data,pos) if flag&8 else 0;pos+=2 if flag&8 else 0
 ext=U32(data,pos) if flag&4 else 0;pos+=4 if flag&4 else 0
 wide=bool(flag&1);length=n*(2 if wide else 1)
 val=data[pos:pos+length].decode('utf-16le' if wide else 'latin1',errors='replace');pos+=length+4*rich+ext
 return val,pos

def sst_strings(recs):
 idx=next((i for i,r in enumerate(recs) if r[1]==0xFC),None)
 if idx is None:return []
 chunks=[recs[idx][2]]
 for r in recs[idx+1:]:
  if r[1]!=0x3C:break
  chunks.append(r[2])
 count=U32(chunks[0],4)
 class Reader:
  def __init__(self):self.i=0;self.p=8
  def advance(self):
   while self.p>=len(chunks[self.i]) and self.i+1<len(chunks):self.i+=1;self.p=0
  def read(self,n):
   out=bytearray()
   while n>0:
    self.advance();available=len(chunks[self.i])-self.p
    if available<=0:raise EOFError()
    take=min(available,n)
    out.extend(chunks[self.i][self.p:self.p+take]);self.p+=take;n-=take
   return bytes(out)
  def chars(self,n,wide):
   out=[]
   while n:
    self.advance()
    available=len(chunks[self.i])-self.p
    chars_avail=min(n,available//(2 if wide else 1))
    if chars_avail<=0:
     if self.i+1>=len(chunks):raise EOFError()
     self.i+=1;self.p=0
     wide=bool(self.read(1)[0]&1)
     continue
    d=self.read(chars_avail*(2 if wide else 1))
    out.append(d.decode('utf-16le' if wide else 'latin1',errors='replace'))
    n-=chars_avail
    if n and self.p==len(chunks[self.i]):
     self.i+=1;self.p=0
     wide=bool(self.read(1)[0]&1)
   return ''.join(out)
 rr=Reader();out=[]
 for i in range(count):
  try:
   n=U16(rr.read(2));flags=rr.read(1)[0]
   rich=U16(rr.read(2)) if flags&8 else 0
   ext=U32(rr.read(4)) if flags&4 else 0
   t=rr.chars(n,bool(flags&1))
   if rich:rr.read(rich*4)
   if ext:rr.read(ext)
   out.append(t)
  except Exception as e:
   print('SST failed at',i,'of',count,'reason',repr(e));break
 return out

def decode_rk(i):
 div=100 if i&1 else 1
 if i&2:
  v=struct.unpack('<i',struct.pack('<I',i&0xfffffffc))[0]>>2
 else:
  v=struct.unpack('<d',b'\0\0\0\0'+struct.pack('<I',i&0xfffffffc))[0]
 return v/div

def xls_dump(path):
 w=OLE(path).open('Workbook')
 r=list(records(w))
 names=[]
 for k,c,d in r:
  if c==0x85:
   ofs=U32(d,0)
   name,_=parse_xl_unicode(d,6,True)
   names.append((name,ofs))
 sst=sst_strings(r)
 sheets={};stats={}
 for si,(name,start) in enumerate(names):
  end=names[si+1][1] if si+1<len(names) else len(w)
  cells={};formula_count=0;codes=defaultdict(int)
  for k,c,d in records(w,start,end):
   codes[hex(c)]+=1
   if c==0xA:break
   if c in (0xFD,0x204,0x203,0x27e,0x06):
    if len(d)<6:continue
    row,col=struct.unpack_from('<HH',d)
    val=None
    if c==0xFD and len(d)>=10:
     sstidx=U32(d,6);val=sst[sstidx] if sstidx<len(sst) else f'[SST {sstidx}]'
    if c==0x204 and len(d)>=8:
     ln=U16(d,6);val=d[8:8+ln].decode('latin1',errors='replace')
    if c==0x203 and len(d)>=14:val=struct.unpack_from('<d',d,6)[0]
    if c==0x27e and len(d)>=10:val=decode_rk(U32(d,6))
    if c==0x06 and len(d)>=14:
     formula_count+=1
     raw=d[6:14]
     if raw[6:8]!=b'\xff\xff':val=struct.unpack('<d',raw)[0]
     else:val='[FORMULA_NON_NUMERIC]'
    if val is not None:cells[row+1,col+1]=val
   if c==0xBD and len(d)>=6:
    row,first=struct.unpack_from('<HH',d)
    last=U16(d,len(d)-2)
    for n,col in enumerate(range(first,last+1)):
     st=4+n*6
     if st+6<=len(d)-2:cells[row+1,col+1]=decode_rk(U32(d,st+2))
  sheets[name]=cells
  stats[name]=(len(cells),formula_count,dict(codes))
 return sheets,stats,len(sst)
if __name__=='__main__':
 import sys
 sheets,stats,ns=xls_dump(sys.argv[1]);print('SST count',ns)
 for s,cs in sheets.items():
  print('\n###',s,stats[s][:2]);
  for row in range(1,80):
   items=[(k[1],str(v)[:100]) for k,v in cs.items() if k[0]==row and v not in ('',' ')];items.sort()
   if items:print(row,items[:28])
