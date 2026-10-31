import json, z3

data = json.load(open("../data/repo_10.json"))

packages = data["packages"]

x = {(p, v): z3.Bool(f"{p}=={v}")
     for p in packages
     for v in packages[p]["versions"]}

nextX = iter(x)
print(next(nextX))

print(x[('ansimarkup', '1.2.0')])

print(x)


