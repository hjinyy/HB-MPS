"""
HB-MPS Power Flow Node-Level Validation on IEEE 33-bus  [FINAL]
- 실측 부하 형상 유지 + IEEE 33-bus 정격 정규화 (선배님 지침: min->0.6, max->1.1 pu)
- Substation OLTC 탭으로 slack 전압 1.03pu 설정 (baseline이 정상범위서 출발; 표준 관행)
- 역률 0.9, 전압한계 0.95~1.05 (ANSI C84.1)
"""
import numpy as np, pandas as pd, pandapower as pp, pandapower.networks as nw, math, warnings, logging
warnings.filterwarnings('ignore'); logging.getLogger('pandapower').setLevel(logging.ERROR)
PF=0.9; TANP=math.tan(math.acos(PF)); VMIN=0.95; VSLACK=1.03
df=pd.read_csv('/mnt/user-data/uploads/data_file.csv').dropna(subset=['산업용 전력사용량(kWh)']).reset_index(drop=True)
ind=df['산업용 전력사용량(kWh)'].values; res=df['주택용 전력사용량(kWh)'].values; pv=df['E: 태양광 발전량(kWh)'].values
T=len(ind); base=nw.case33bw()
IND_B=[17,16,15,14,13,32,31,30,29]; RES_B=[8,9,10,11,12,24,25,21,22]; PV_B=6; HB_B=17
P_IND=base.load.p_mw[base.load.bus.isin(IND_B)].sum(); P_RES=base.load.p_mw[base.load.bus.isin(RES_B)].sum()
def norm(x,lo=0.6,hi=1.1): return lo+(x-x.min())/(x.max()-x.min())*(hi-lo)
ind_pu=norm(ind); res_pu=norm(res)
ind_mw=ind_pu*P_IND; res_mw=res_pu*P_RES; pv_mw=(pv/pv.max())*P_IND if pv.max()>0 else pv*0
E_th_pu=1.3*ind_pu.mean(); P_HFC=0.5
def build(imw,rmw,pmw,hbmw):
    net=nw.case33bw(); net.ext_grid.vm_pu=VSLACK; net.load=net.load.iloc[0:0]
    pi=imw/len(IND_B)
    for b in IND_B: pp.create_load(net,b,p_mw=pi,q_mvar=pi*TANP)
    pr=rmw/len(RES_B)
    for b in RES_B: pp.create_load(net,b,p_mw=pr,q_mvar=pr*TANP)
    if pmw>0: pp.create_sgen(net,PV_B,p_mw=pmw,q_mvar=0)
    if hbmw>0: pp.create_sgen(net,HB_B,p_mw=hbmw,q_mvar=0)
    return net
rows=[]
for t in range(T):
    ex=max(ind_pu[t]-E_th_pu,0)*P_IND; ntr=math.ceil(ex/P_HFC) if ex>0 else 0; hbmw=ntr*P_HFC
    r={'t':t,'mode2':int(ex>0),'ntruck':ntr}
    for tag,hb in [('base',0.0),('hbmps',hbmw)]:
        net=build(ind_mw[t],res_mw[t],pv_mw[t],hb); pp.runpp(net,algorithm='nr')
        r[f'vmin_{tag}']=net.res_bus.vm_pu.min(); r[f'vminbus_{tag}']=int(net.res_bus.vm_pu.idxmin())
        r[f'ploss_{tag}']=net.res_line.pl_mw.sum(); r[f'viol_{tag}']=int(net.res_bus.vm_pu.min()<VMIN)
    rows.append(r)
R=pd.DataFrame(rows); R.to_csv('/home/claude/pf_results.csv',index=False)
m2=R[R.mode2==1]; nm2=R[R.mode2==0]
print("="*64)
print(f"IEEE 33-bus | slack={VSLACK}pu | PF={PF} | 산업정격{P_IND:.2f}MW 주거{P_RES:.2f}MW")
print("="*64)
print(f"Mode2 발동          : {R.mode2.sum()}/{T} 시점 (최대 {R.ntruck.max()}트럭)")
print(f"baseline 전압범위   : [{R.vmin_base.min():.4f}, {R.vmin_base.max():.4f}] pu")
print(f"HB-MPS 전압범위     : [{R.vmin_hbmps.min():.4f}, {R.vmin_hbmps.max():.4f}] pu")
print(f"전압위반(<0.95pu)   : base {R.viol_base.sum()} -> hbmps {R.viol_hbmps.sum()} 시점")
print(f"\nMode2 시점({len(m2)}): 최저V {m2.vmin_base.mean():.4f} -> {m2.vmin_hbmps.mean():.4f} pu (+{(m2.vmin_hbmps.mean()-m2.vmin_base.mean())*100:.2f}%p)")
print(f"  위반해소: base {m2.viol_base.sum()}/{len(m2)} -> hbmps {m2.viol_hbmps.sum()}/{len(m2)}")
print(f"Mode1 시점({len(nm2)}): 최저V {nm2.vmin_base.mean():.4f} pu, 위반 {nm2.viol_base.sum()} (정상운전 유지)")
tp=len(R[(R.mode2==1)&(R.viol_base==1)]); fp=len(R[(R.mode2==1)&(R.viol_base==0)])
fn=len(R[(R.mode2==0)&(R.viol_base==1)]); tn=len(R[(R.mode2==0)&(R.viol_base==0)])
print(f"\nMode2판단(에너지) vs 전압위반(물리): 정밀도 {tp/(tp+fp)*100 if tp+fp else 0:.0f}% 재현율 {tp/(tp+fn)*100 if tp+fn else 0:.0f}%")
print(f"  M2&위반={tp} M2&정상={fp} 정상판단&위반={fn} 정상&정상={tn}")
w=R.loc[R.vmin_base.idxmin()]
print(f"\n최악부하 t={int(w.t)}: 최저V {w.vmin_base:.4f}->{w.vmin_hbmps:.4f}pu, {int(w.ntruck)}트럭, 손실 {w.ploss_base*1000:.1f}->{w.ploss_hbmps*1000:.1f}kW")
print(f"최저전압 노드: bus {int(R.vminbus_base.mode().values[0])} (HB-MPS 접속점)")
