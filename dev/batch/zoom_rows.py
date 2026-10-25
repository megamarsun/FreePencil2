"""作例の 4 枚(3D/白/材質/セル)から同じ割合の範囲を切り出して横に並べる。
python zoom_rows.py <dir> <out.png> name:x0,y0,x1,y1 ...  (割合)"""
import sys
from pathlib import Path
from PIL import Image
D=Path(sys.argv[1])
def load(p):
    im=Image.open(p).convert("RGBA"); bg=Image.new("RGBA",im.size,"white"); return Image.alpha_composite(bg,im).convert("RGB")
rows=[]
for spec in sys.argv[3:]:
    n,b=spec.split(":"); box=[float(v) for v in b.split(",")]
    c=[]
    for f in ("0_3d.png","1_WHITE.png","2_NONE.png","3_CEL.png"):
        im=load(D/n/f); W,H=im.size
        x=im.crop((int(box[0]*W),int(box[1]*H),int(box[2]*W),int(box[3]*H)))
        c.append(x.resize((int(x.width*480/x.height),480)))
    row=Image.new("RGB",(sum(x.width for x in c)+30,480),"white"); X=0
    for x in c: row.paste(x,(X,0)); X+=x.width+10
    rows.append(row)
S=Image.new("RGB",(max(r.width for r in rows),sum(r.height+10 for r in rows)),"white"); Y=0
for r in rows: S.paste(r,(0,Y)); Y+=r.height+10
S.save(sys.argv[2]); print(S.size)
