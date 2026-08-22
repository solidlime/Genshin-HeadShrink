from pathlib import Path
total = 0
total_files = 0
for p in sorted(Path('.').iterdir()):
    if p.is_dir():
        sz = sum(f.stat().st_size for f in p.rglob('*') if f.is_file()) / (1024*1024)
        n = sum(1 for _ in p.rglob('*') if _.is_file())
        log = (p / 'log.txt').exists()
        log_sz = (p / 'log.txt').stat().st_size / (1024*1024) if log else 0
        print(f'{p.name:<15}  size={sz:>7.1f}MB  files={n:>5}  log.txt={log_sz:.2f}MB')
        total += sz
        total_files += n
print(f'--- total: {total:.1f}MB / {total_files} files ---')
