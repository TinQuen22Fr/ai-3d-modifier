from fastapi import FastAPI, APIRouter, UploadFile, File, Form, HTTPException
from fastapi.responses import Response, StreamingResponse
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorGridFSBucket
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
from pathlib import Path
from datetime import datetime, timezone
import os
import re
import json
import uuid
import base64
import asyncio
import logging

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env")

from cad_engine import load_mesh, repair, mesh_stats, render_views, point_info, run_script, to_stl_bytes  # noqa: E402
from components_default import DEFAULT_COMPONENTS, DIM_LABELS  # noqa: E402
from prompts import build_system_prompt, build_user_prompt  # noqa: E402
from emergentintegrations.llm.chat import LlmChat, UserMessage, ImageContent, TextDelta, StreamDone  # noqa: E402

mongo_url = os.environ["MONGO_URL"]
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ["DB_NAME"]]
fs = AsyncIOMotorGridFSBucket(db, bucket_name="stlfiles")
LLM_KEY = os.environ.get("EMERGENT_LLM_KEY", "")

MODELS = {
    "claude-sonnet-4-5": ("anthropic", "claude-sonnet-4-5-20250929", "Claude Sonnet 4.5"),
    "gemini-3-flash": ("gemini", "gemini-3-flash-preview", "Gemini 3 Flash"),
    "gemini-3.1-pro": ("gemini", "gemini-3.1-pro-preview", "Gemini 3.1 Pro"),
}
MAX_ATTEMPTS = 3
MAX_UPLOAD = 60 * 1024 * 1024

app = FastAPI()
api = APIRouter(prefix="/api")
logger = logging.getLogger("stl")
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")


def now():
    return datetime.now(timezone.utc).isoformat()


def clean(doc):
    if doc is None:
        return None
    doc = dict(doc)
    doc.pop("_id", None)
    return doc


async def put_file(data: bytes, name: str, ctype: str) -> str:
    fid = await fs.upload_from_stream(name, data, metadata={"contentType": ctype})
    return str(fid)


async def get_file(fid: str) -> bytes:
    from bson import ObjectId
    stream = await fs.open_download_stream(ObjectId(fid))
    return await stream.read()


async def del_file(fid: Optional[str]):
    from bson import ObjectId
    if not fid:
        return
    try:
        await fs.delete(ObjectId(fid))
    except Exception:
        pass


async def create_version(project_id: str, mesh, source: str, label: str, parent_id=None, script=None, prompt=None):
    stl = await asyncio.to_thread(to_stl_bytes, mesh)
    stats = await asyncio.to_thread(mesh_stats, mesh)
    png = await asyncio.to_thread(render_views, mesh)
    count = await db.versions.count_documents({"project_id": project_id})
    vid = str(uuid.uuid4())
    doc = {
        "id": vid, "project_id": project_id, "number": count + 1, "parent_id": parent_id,
        "source": source, "label": label, "script": script, "prompt": prompt, "stats": stats,
        "stl_file": await put_file(stl, f"{vid}.stl", "model/stl"),
        "render_file": await put_file(png, f"{vid}.png", "image/png"),
        "created_at": now(),
    }
    await db.versions.insert_one(doc)
    await db.projects.update_one({"id": project_id}, {"$set": {"current_version_id": vid, "updated_at": now()}})
    return clean(doc)


async def get_components():
    items = await db.components.find({}, {"_id": 0}).sort("created_at", 1).to_list(500)
    return items


# ---------------- Components ----------------
class ComponentIn(BaseModel):
    name: str
    category: str = "Ecran"
    description: str = ""
    dims: Dict[str, float]


@api.get("/")
async def root():
    return {"message": "Atelier STL IA"}


@api.get("/models")
async def list_models():
    return [{"id": k, "label": v[2]} for k, v in MODELS.items()]


@api.get("/components")
async def list_components():
    return {"items": await get_components(), "labels": DIM_LABELS}


@api.post("/components")
async def add_component(c: ComponentIn):
    slug = re.sub(r"[^a-z0-9]+", "_", c.name.lower()).strip("_")[:30] or "module"
    doc = {"id": f"{slug}_{uuid.uuid4().hex[:4]}", **c.model_dump(), "builtin": False, "created_at": now()}
    await db.components.insert_one(doc)
    return clean(doc)


@api.put("/components/{cid}")
async def update_component(cid: str, c: ComponentIn):
    r = await db.components.update_one({"id": cid}, {"$set": c.model_dump()})
    if not r.matched_count:
        raise HTTPException(404, "Composant introuvable")
    return clean(await db.components.find_one({"id": cid}))


@api.delete("/components/{cid}")
async def delete_component(cid: str):
    await db.components.delete_one({"id": cid})
    return {"ok": True}


# ---------------- Projects ----------------
@api.post("/projects")
async def create_project(file: UploadFile = File(...), name: str = Form("")):
    data = await file.read()
    if len(data) > MAX_UPLOAD:
        raise HTTPException(413, "Fichier trop volumineux (max 60 Mo)")
    if not (file.filename or "").lower().endswith(".stl"):
        raise HTTPException(400, "Seuls les fichiers .stl sont acceptés")
    try:
        mesh = await asyncio.to_thread(lambda: repair(load_mesh(data)))
    except Exception as e:
        raise HTTPException(400, f"STL illisible : {e}")
    pid = str(uuid.uuid4())
    pname = name.strip() or Path(file.filename).stem
    await db.projects.insert_one({"id": pid, "name": pname, "filename": file.filename, "current_version_id": None,
                                  "created_at": now(), "updated_at": now()})
    await create_version(pid, mesh, "upload", "Fichier original")
    return await project_detail(pid)


@api.get("/projects")
async def list_projects():
    items = await db.projects.find({}, {"_id": 0}).sort("updated_at", -1).to_list(200)
    for p in items:
        p["versions_count"] = await db.versions.count_documents({"project_id": p["id"]})
    return items


@api.get("/projects/{pid}")
async def project_detail(pid: str):
    p = await db.projects.find_one({"id": pid}, {"_id": 0})
    if not p:
        raise HTTPException(404, "Projet introuvable")
    p["versions"] = await db.versions.find({"project_id": pid}, {"_id": 0}).sort("number", 1).to_list(500)
    p["messages"] = await db.messages.find({"project_id": pid}, {"_id": 0}).sort("created_at", 1).to_list(1000)
    return p


class RenameIn(BaseModel):
    name: str


@api.patch("/projects/{pid}")
async def rename_project(pid: str, body: RenameIn):
    await db.projects.update_one({"id": pid}, {"$set": {"name": body.name.strip() or "Sans nom", "updated_at": now()}})
    return {"ok": True}


@api.delete("/projects/{pid}")
async def delete_project(pid: str):
    async for v in db.versions.find({"project_id": pid}):
        await del_file(v.get("stl_file"))
        await del_file(v.get("render_file"))
    await db.versions.delete_many({"project_id": pid})
    await db.messages.delete_many({"project_id": pid})
    await db.projects.delete_one({"id": pid})
    return {"ok": True}


class CurrentIn(BaseModel):
    version_id: str


@api.post("/projects/{pid}/current")
async def set_current(pid: str, body: CurrentIn):
    v = await db.versions.find_one({"id": body.version_id, "project_id": pid})
    if not v:
        raise HTTPException(404, "Version introuvable")
    await db.projects.update_one({"id": pid}, {"$set": {"current_version_id": body.version_id, "updated_at": now()}})
    return {"ok": True}


@api.post("/projects/{pid}/versions")
async def upload_version(pid: str, file: UploadFile = File(...)):
    p = await db.projects.find_one({"id": pid})
    if not p:
        raise HTTPException(404, "Projet introuvable")
    data = await file.read()
    try:
        mesh = await asyncio.to_thread(lambda: repair(load_mesh(data)))
    except Exception as e:
        raise HTTPException(400, f"STL illisible : {e}")
    return await create_version(pid, mesh, "upload", f"Import : {file.filename}", parent_id=p.get("current_version_id"))


async def _version_mesh(vid: str):
    v = await db.versions.find_one({"id": vid})
    if not v:
        raise HTTPException(404, "Version introuvable")
    data = await get_file(v["stl_file"])
    return v, data


@api.get("/versions/{vid}/stl")
async def version_stl(vid: str, download: int = 0):
    v, data = await _version_mesh(vid)
    p = await db.projects.find_one({"id": v["project_id"]}) or {}
    safe = re.sub(r"[^A-Za-z0-9_-]+", "_", p.get("name", "piece"))
    headers = {"Cache-Control": "public, max-age=31536000"}
    if download:
        headers["Content-Disposition"] = f'attachment; filename="{safe}_v{v["number"]}.stl"'
    return Response(content=data, media_type="model/stl", headers=headers)


@api.get("/versions/{vid}/render")
async def version_render(vid: str):
    v = await db.versions.find_one({"id": vid})
    if not v:
        raise HTTPException(404, "Version introuvable")
    return Response(content=await get_file(v["render_file"]), media_type="image/png")


class PointIn(BaseModel):
    version_id: str
    point: List[float]


@api.post("/point-info")
async def api_point_info(body: PointIn):
    _, data = await _version_mesh(body.version_id)
    mesh = await asyncio.to_thread(load_mesh, data)
    return await asyncio.to_thread(point_info, mesh, body.point)


# ---------------- Chat IA ----------------
class ChatIn(BaseModel):
    message: str
    model: str = "claude-sonnet-4-5"
    points: List[Dict[str, Any]] = []
    version_id: Optional[str] = None


CODE_RE = re.compile(r"```(?:python|py)?\s*\n(.*?)```", re.S)


def extract_code(text: str) -> Optional[str]:
    blocks = CODE_RE.findall(text or "")
    blocks = [b for b in blocks if "result" in b]
    return blocks[-1].strip() if blocks else None


def sse(obj):
    return f"data: {json.dumps(obj, ensure_ascii=False)}\n\n"


@api.post("/projects/{pid}/chat")
async def chat(pid: str, body: ChatIn):
    p = await db.projects.find_one({"id": pid})
    if not p:
        raise HTTPException(404, "Projet introuvable")
    if body.model not in MODELS:
        raise HTTPException(400, "Modele inconnu")
    base_vid = body.version_id or p.get("current_version_id")
    base_v, base_stl = await _version_mesh(base_vid)
    history = await db.messages.find({"project_id": pid}, {"_id": 0}).sort("created_at", -1).to_list(8)
    history.reverse()

    user_msg = {"id": str(uuid.uuid4()), "project_id": pid, "role": "user", "content": body.message,
                "points": body.points, "model": body.model, "base_version_id": base_vid, "created_at": now()}
    await db.messages.insert_one(dict(user_msg))

    async def gen():
        provider, model_name, label = MODELS[body.model]
        full_text = ""
        status, new_version, script, err_text = "info", None, None, None
        try:
            yield sse({"type": "user", "message": clean(user_msg)})
            yield sse({"type": "status", "text": "Analyse de la pièce (vues, cotes, points)..."})
            mesh = await asyncio.to_thread(load_mesh, base_stl)
            stats = mesh_stats(mesh)
            pts = []
            for pt in body.points[:8]:
                coords = pt.get("point") if isinstance(pt, dict) else pt
                info = await asyncio.to_thread(point_info, mesh, coords)
                info["note"] = (pt.get("note") if isinstance(pt, dict) else "") or ""
                pts.append(info)
            png = await asyncio.to_thread(render_views, mesh, pts)
            components = await get_components()
            prompt = build_user_prompt(body.message, stats, pts, history, base_v)
            system = build_system_prompt(components)

            chat_llm = LlmChat(api_key=LLM_KEY, session_id=f"{pid}-{uuid.uuid4().hex[:8]}", system_message=system)
            chat_llm.with_model(provider, model_name)
            msg = UserMessage(text=prompt, file_contents=[ImageContent(image_base64=base64.b64encode(png).decode())])

            for attempt in range(1, MAX_ATTEMPTS + 1):
                yield sse({"type": "status", "text": f"{label} réfléchit..." if attempt == 1 else f"Correction automatique (tentative {attempt}/{MAX_ATTEMPTS})..."})
                if attempt > 1:
                    sep = f"\n\n---\n**Correction automatique (tentative {attempt})**\n\n"
                    full_text += sep
                    yield sse({"type": "delta", "text": sep})
                reply = ""
                async for ev in chat_llm.stream_message(msg):
                    if isinstance(ev, TextDelta):
                        reply += ev.content
                        full_text += ev.content
                        yield sse({"type": "delta", "text": ev.content})
                    elif isinstance(ev, StreamDone):
                        break
                code = extract_code(reply)
                if not code:
                    status = "info"
                    break
                yield sse({"type": "status", "text": "Exécution du script de modélisation..."})
                res = await run_script(base_stl, code, components)
                if res.get("ok"):
                    out_mesh = await asyncio.to_thread(load_mesh, res["stl"])
                    yield sse({"type": "status", "text": "Génération de la nouvelle version..."})
                    short = body.message.strip().replace("\n", " ")
                    new_version = await create_version(pid, out_mesh, "ai", short[:80] + ("..." if len(short) > 80 else ""),
                                                       parent_id=base_vid, script=code, prompt=body.message)
                    script, status = code, "ok"
                    if not out_mesh.is_watertight:
                        warn = "\n\n> Attention : le résultat n'est pas parfaitement étanche (manifold). Vérifiez-le dans votre trancheur."
                        full_text += warn
                        yield sse({"type": "delta", "text": warn})
                    yield sse({"type": "version", "version": new_version})
                    break
                err_text = res.get("error", "Erreur inconnue")
                yield sse({"type": "exec_error", "text": err_text})
                script = code
                status = "error"
                msg = UserMessage(text=(
                    "Le script a echoue a l'execution avec cette erreur :\n```\n" + err_text + "\n" +
                    (res.get("traceback") or "")[-1500:] + "\n```\nCorrige le script. Reponds avec une tres courte explication en francais "
                    "puis le script complet corrige dans un bloc ```python```."))
        except Exception as e:
            logger.exception("chat error")
            status, err_text = "error", str(e)
            yield sse({"type": "error", "text": f"Erreur : {e}"})
        amsg = {"id": str(uuid.uuid4()), "project_id": pid, "role": "assistant", "content": full_text, "status": status,
                "error": err_text if status == "error" else None, "script": script, "model": body.model,
                "version_id": new_version["id"] if new_version else None,
                "version_number": new_version["number"] if new_version else None, "created_at": now()}
        await db.messages.insert_one(dict(amsg))
        await db.projects.update_one({"id": pid}, {"$set": {"updated_at": now()}})
        yield sse({"type": "done", "message": clean(amsg)})

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@api.delete("/projects/{pid}/messages")
async def clear_messages(pid: str):
    await db.messages.delete_many({"project_id": pid})
    return {"ok": True}


app.include_router(api)
app.add_middleware(CORSMiddleware, allow_credentials=True, allow_origins=os.environ.get("CORS_ORIGINS", "*").split(","),
                   allow_methods=["*"], allow_headers=["*"])


@app.on_event("startup")
async def seed():
    for c in DEFAULT_COMPONENTS:
        await db.components.update_one({"id": c["id"]}, {"$setOnInsert": {**c, "created_at": now()}}, upsert=True)


@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()
