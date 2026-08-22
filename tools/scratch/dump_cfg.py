import json
cfg=json.load(open(r"G:\XXMI-Launcher-Portable\Tools\HeadShrink\scripts\config.json",encoding='utf-8'))
def walk(o,path=''):
    if isinstance(o,dict):
        for k,v in o.items():
            if isinstance(k,str) and len(k)==8 and all(c in '0123456789abcdef' for c in k):
                print(path,k,'->',v if isinstance(v,str) else type(v).__name__)
            walk(v,path+'/'+str(k)[:30])
    elif isinstance(o,list):
        pass
walk(cfg)
print('---units keys---')
u=cfg.get('__config__',{})
print(list(u.keys())[:20])
