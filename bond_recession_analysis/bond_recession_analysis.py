import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from pathlib import Path

# Dosya yolları (aynı klasöre koy)
dgs10_path = Path('DGS10.csv')
dgs2_path  = Path('DGS2.csv')
usrec_path = Path('USREC.csv')

# Oku
dgs10 = pd.read_csv(dgs10_path)
dgs2  = pd.read_csv(dgs2_path)
usrec = pd.read_csv(usrec_path)

# normalize date column (FRED csv'leri observation_date kullanıyor olabilir)
for df in (dgs10, dgs2, usrec):
    if 'observation_date' in df.columns:
        df.rename(columns={'observation_date':'DATE'}, inplace=True)
    df['DATE'] = pd.to_datetime(df['DATE'])

# Rename columns if needed (FRED default sütun isimleri DGS10, DGS2, USREC)
dgs10 = dgs10[['DATE', [c for c in dgs10.columns if 'DGS10' in c][0]]] if any('DGS10' in c for c in dgs10.columns) else dgs10
dgs2  = dgs2[['DATE', [c for c in dgs2.columns if 'DGS2' in c][0]]] if any('DGS2' in c for c in dgs2.columns) else dgs2
usrec = usrec[['DATE', [c for c in usrec.columns if 'USREC' in c][0]]] if any('USREC' in c for c in usrec.columns) else usrec

dgs10.columns = ['DATE','DGS10']
dgs2.columns  = ['DATE','DGS2']
usrec.columns = ['DATE','USREC']

# Merge
df = dgs10.merge(dgs2, on='DATE', how='inner').merge(usrec, on='DATE', how='inner')
df = df.sort_values('DATE').reset_index(drop=True)

# Spread & inversion
df['spread'] = df['DGS10'] - df['DGS2']
df['inverted'] = df['spread'] < 0
df['inverted_prev'] = df['inverted'].shift(1).fillna(False)

# Find inversion intervals
starts = df[(df['inverted']==True) & (df['inverted_prev']==False)]['DATE'].tolist()
ends   = df[(df['inverted']==False) & (df['inverted_prev']==True)]['DATE'].tolist()
if len(ends) < len(starts):
    ends.append(df['DATE'].iloc[-1])
inversions = pd.DataFrame({'start': starts, 'end': ends})
inversions['dis_inversion_date'] = inversions['end']

# Recession starts from USREC (0->1 transitions)
usrec_sorted = usrec.sort_values('DATE').reset_index(drop=True)
usrec_sorted['prev'] = usrec_sorted['USREC'].shift(1).fillna(0).astype(int)
recession_starts = usrec_sorted[(usrec_sorted['USREC']==1) & (usrec_sorted['prev']==0)]['DATE'].tolist()

def find_recession_within(dis_date, months=24):
    limit = dis_date + pd.DateOffset(months=months)
    future = [r for r in recession_starts if dis_date < r <= limit]
    if future:
        return True, future[0]
    return False, pd.NaT

records = []
for _, row in inversions.iterrows():
    dis = row['dis_inversion_date']
    found, rdate = find_recession_within(dis, months=24)
    days = (rdate - dis).days if pd.notna(rdate) else np.nan
    records.append({'dis_inversion_date': dis, 'recession_within_24m': found, 'recession_start_date': rdate, 'days_to_recession': days})

res_df = pd.DataFrame(records)
total = len(res_df)
hits = int(res_df['recession_within_24m'].sum()) if total>0 else 0
false = total - hits
hit_rate = hits/total if total>0 else np.nan
signal_stats = pd.DataFrame([{'total_dis_inversions': total, 'true_signals': hits, 'false_signals': false, 'hit_rate': hit_rate}])

# Export Excel
output_path = Path('yieldcurve_analysis_complete.xlsx')
with pd.ExcelWriter(output_path) as writer:
    df.to_excel(writer, sheet_name='full_data', index=False)
    inversions.to_excel(writer, sheet_name='inversions', index=False)
    res_df.to_excel(writer, sheet_name='recession_links', index=False)
    signal_stats.to_excel(writer, sheet_name='signal_analysis', index=False)
    pd.DataFrame([{'note':'Provide Fed funds / policy rate timeseries to compute correllation with spread.'}]).to_excel(writer, sheet_name='fed_cycle_notes', index=False)

print("Saved:", output_path.resolve())
print("\nSignal summary:\n", signal_stats.to_string(index=False))
print("\nInversion preview:\n", inversions.head(10).to_string(index=False))
print("\nDis-inversion -> recession links:\n", res_df.to_string(index=False))

# Plot
plt.figure(figsize=(12,5))
plt.plot(df['DATE'], df['spread'], label='10y-2y spread', linewidth=1.2)
plt.axhline(0, linewidth=0.8)
for _, r in inversions.iterrows():
    plt.axvspan(r['start'], r['end'], alpha=0.12, color='orange')
rec_period = df[df['USREC']==1]
if not rec_period.empty:
    groups = (rec_period['DATE'].diff() > pd.Timedelta(days=1)).cumsum()
    for _, g in rec_period.groupby(groups):
        plt.axvspan(g['DATE'].iloc[0], g['DATE'].iloc[-1], alpha=0.18, color='gray')
plt.title('10y - 2y spread with inversions and NBER recessions')
plt.ylabel('Spread (percentage points)')
plt.grid(True)
plt.tight_layout()
plt.show()
