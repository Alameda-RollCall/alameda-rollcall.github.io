"""Write votes.json compactly but diff-friendly: one vote per line.

The file is fetched by every visitor, so it is written without indentation; one
vote per line keeps git diffs readable when a meeting is added.
"""
import json


def write_data(path, data):
    dumps = lambda x: json.dumps(x, ensure_ascii=False, separators=(",", ":"))
    parts = []
    for key, value in data.items():
        if key == "votes":
            body = "[\n" + ",\n".join(dumps(v) for v in value) + "\n]"
        else:
            body = dumps(value)
        parts.append(f'{dumps(key)}:{body}')
    with open(path, "w", encoding="utf-8") as f:
        f.write("{\n" + ",\n".join(parts) + "\n}\n")
