#!/usr/bin/env python3
"""dissolve済みGeoJSONのpropertiesを、指定フィールドを結合したnameだけに絞る。"""

import json
import sys


def main() -> None:
    in_path, out_path, fields_csv = sys.argv[1], sys.argv[2], sys.argv[3]
    fields = fields_csv.split(",")

    data = json.load(open(in_path))
    for feature in data["features"]:
        props = feature["properties"]
        name = "".join(props.get(f) or "" for f in fields)
        feature["properties"] = {"name": name}

    json.dump(data, open(out_path, "w"), ensure_ascii=False)


if __name__ == "__main__":
    main()
