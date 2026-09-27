from __future__ import annotations

import base64
import json
from importlib.resources import files

from raidio_scene.package import SceneBundle


def preview_html(bundle: SceneBundle) -> str:
    document = files("raidio_scene").joinpath("preview.html").read_text()
    document = document.replace(
        "__MOTION_CODE__", files("raidio_scene").joinpath("motion.js").read_text()
    )
    value = bundle.manifest.model_dump(mode="json", by_alias=True)
    for key, resource in value["resources"].items():
        encoded = base64.b64encode(bundle.resources[key]).decode("ascii")
        resource["data"] = f"data:{resource['mediaType']};base64,{encoded}"
    # JSON is inert text, including user-authored titles containing </script>.
    encoded_json = json.dumps(value).replace("<", "\\u003c").replace("&", "\\u0026")
    return document.replace("__SCENE_DATA__", encoded_json)
