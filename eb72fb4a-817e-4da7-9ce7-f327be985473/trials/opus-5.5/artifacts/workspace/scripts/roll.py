import sys,json
sys.argv=['x']
exec(open('/workspace/scripts/engine.py').read().split('# rolling')[0].replace("for sn in INSCOPE:","for sn in TARGET:").replace("out=[]; detail=[]","out=[]; detail=[]\nimport builtins\nDAYS={}"),globals()) if False else None
