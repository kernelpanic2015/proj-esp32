from pathlib import Path
p=Path('scripts/smoke_update_scheduler.sh')
s=p.read_text()
old='''grep -q '\"version\":\"0.1.16\"' <<<\"$V\"\ngrep -q '\"build\":17' <<<\"$V\"'''
new='''grep -q '\"version\":\"0.1.14\"' <<<\"$V\"\ngrep -q '\"build\":15' <<<\"$V\"'''
if old not in s:
    raise SystemExit('baseline assertion block not found')
s=s.replace(old,new,1)
p.write_text(s)
print('STAGE6A_SMOKE_BASELINE_FIXED')
