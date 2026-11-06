"""ひざの向きの崩れを探す: ひざが足先の向きから 50 度を超えてずれたコマ(曲がり 20 度以上)を出す。  python kneedir.py <ks.npz>"""
import sys, numpy as np
z=np.load(sys.argv[1]); P=z['P']; fr=z['frames']
for s,o in (("L",0),("R",4)):
    H,K,A,T=P[:,o],P[:,o+1],P[:,o+2],P[:,o+3]
    u=(A-H)/np.linalg.norm(A-H,axis=1,keepdims=True)
    p=(K-H)-u*np.sum((K-H)*u,1,keepdims=True)
    f=(T-A)-u*np.sum((T-A)*u,1,keepdims=True)
    bend=180-np.degrees(np.arccos(np.clip(np.sum((H-K)*(A-K),1)/np.linalg.norm(H-K,axis=1)/np.linalg.norm(A-K,axis=1),-1,1)))
    ang=np.degrees(np.arccos(np.clip(np.sum(p*f,1)/(np.linalg.norm(p,axis=1)*np.linalg.norm(f,axis=1)+1e-9),-1,1)))
    bad=(bend>20)&(ang>50)
    idx=fr[bad]
    runs=[];
    for i in idx:
        if runs and i-runs[-1][1]<=2: runs[-1][1]=i
        else: runs.append([i,i])
    print(s,len(idx),[(a,b,int(ang[fr==a][0])) for a,b in runs][:40])
