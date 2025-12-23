# Maya Python UI: Random Triangulate (lock axes selectable + boundary lock)
import maya.cmds as cmds
import random
import re

WIN_NAME = "mokaRandomTriangulateUI"

def _get_mesh_transforms_from_selection():
    sel = cmds.ls(sl=True, long=True) or []
    out, seen = [], set()

    for s in sel:
        # component -> transform
        if "." in s:
            s = s.split(".", 1)[0]

        # shape -> parent transform
        if cmds.objExists(s) and cmds.nodeType(s) == "mesh":
            p = cmds.listRelatives(s, parent=True, fullPath=True) or []
            if p:
                s = p[0]

        if not cmds.objExists(s) or cmds.nodeType(s) != "transform":
            continue

        shapes = cmds.listRelatives(s, shapes=True, fullPath=True, type="mesh") or []
        # intermediate shapes除外
        shapes = [sh for sh in shapes if not cmds.getAttr(sh + ".intermediateObject")]

        if shapes and s not in seen:
            out.append(s); seen.add(s)

    return out

def _boundary_vertex_indices(obj):
    """Boundary edges (connected to exactly 1 face) -> collect their vertex indices."""
    boundary_verts = set()
    edge_count = cmds.polyEvaluate(obj, edge=True) or 0

    for e in range(edge_count):
        edge = f"{obj}.e[{e}]"
        info = cmds.polyInfo(edge, edgeToFace=True)
        if not info:
            continue

        line = info[0].strip()
        if ":" not in line:
            continue

        right = line.split(":", 1)[1].strip()
        faces = []
        for t in right.split():
            try:
                faces.append(int(t))
            except Exception:
                pass

        # boundary edge if only one face is connected
        if len(faces) != 1:
            continue

        vinfo = cmds.polyInfo(edge, edgeToVertex=True)
        if not vinfo:
            continue

        nums = re.findall(r"\d+", vinfo[0])
        # nums example: ["5","12","13"] -> first is edge index, rest are vertex indices
        for n in nums[1:]:
            boundary_verts.add(int(n))

    return boundary_verts

def _edge_to_faces(obj, e_index):
    info = cmds.polyInfo(f"{obj}.e[{e_index}]", edgeToFace=True) or []
    if not info:
        return []
    line = info[0].strip()
    if ":" not in line:
        return []
    right = line.split(":", 1)[1].strip()
    faces = []
    for t in right.split():
        try:
            faces.append(int(t))
        except Exception:
            pass
    return faces

def random_triangulate_with_options(
    jitter_amount=0.02,
    seed=1,
    lock_axes=(False, True, False),   # (lockX, lockY, lockZ) True means "do NOT move that axis"
    lock_boundary=True,
    do_triangulate=True,
    do_flip=False,
    flip_probability=0.8,
    flip_iterations=3,
    keep_history=True,
    use_object_space=False
):
    """
    Randomize vertices (internal-only if lock_boundary) by moving ONLY unlocked axes,
    then triangulate, then optionally random flip edges.
    """
    objs = _get_mesh_transforms_from_selection()
    if not objs:
        cmds.warning("ポリゴンメッシュを選択してから実行してください（オブジェクト/コンポーネントどちらでもOK）。")
        return

    lockX, lockY, lockZ = lock_axes
    jitter_amount = float(jitter_amount)
    flip_probability = float(flip_probability)
    flip_iterations = max(1, int(flip_iterations))

    random.seed(int(seed))

    cmds.undoInfo(openChunk=True)
    try:
        for obj in objs:
            boundary = _boundary_vertex_indices(obj) if lock_boundary else set()
            vtx_count = cmds.polyEvaluate(obj, vertex=True) or 0

            moved = 0
            for i in range(vtx_count):
                if i in boundary:
                    continue

                comp = f"{obj}.vtx[{i}]"

                # get current position
                if use_object_space:
                    x, y, z = cmds.xform(comp, q=True, os=True, t=True)
                else:
                    x, y, z = cmds.xform(comp, q=True, ws=True, t=True)

                # compute delta per axis (only if axis is NOT locked)
                dx = 0.0 if lockX else random.uniform(-jitter_amount, jitter_amount)
                dy = 0.0 if lockY else random.uniform(-jitter_amount, jitter_amount)
                dz = 0.0 if lockZ else random.uniform(-jitter_amount, jitter_amount)

                # skip if all locked (no movement)
                if dx == 0.0 and dy == 0.0 and dz == 0.0:
                    continue

                # set new position
                if use_object_space:
                    cmds.xform(comp, os=True, t=(x + dx, y + dy, z + dz))
                else:
                    cmds.xform(comp, ws=True, t=(x + dx, y + dy, z + dz))

                moved += 1

            # triangulate
            if do_triangulate:
                cmds.polyTriangulate(f"{obj}.f[:]", ch=keep_history)

            # optional: random edge flips (only some edges are flippable; that's OK)
            flipped = 0
            if do_flip:
                edge_count = cmds.polyEvaluate(obj, edge=True) or 0
                for _ in range(flip_iterations):
                    for e in range(edge_count):
                        if random.random() > flip_probability:
                            continue
                        faces = _edge_to_faces(obj, e)
                        if len(faces) != 2:
                            continue
                        try:
                            cmds.polyFlipEdge(f"{obj}.e[{e}]", ch=keep_history)
                            flipped += 1
                        except Exception:
                            pass

            if not keep_history:
                cmds.delete(obj, ch=True)

            msg = f"{obj} | moved_vtx={moved}" + (f" | flipped={flipped}" if do_flip else "")
            print(msg)
            cmds.inViewMessage(amg=msg, pos="midCenterTop", fade=True)

    finally:
        cmds.undoInfo(closeChunk=True)

# ---------------- UI ----------------

def _ui_on_run(*_):
    jitter = cmds.floatField("mokaRT_jitter", q=True, v=True)
    seed = cmds.intField("mokaRT_seed", q=True, v=True)

    lockX = cmds.checkBox("mokaRT_lockX", q=True, v=True)
    lockY = cmds.checkBox("mokaRT_lockY", q=True, v=True)
    lockZ = cmds.checkBox("mokaRT_lockZ", q=True, v=True)

    lockBoundary = cmds.checkBox("mokaRT_lockBoundary", q=True, v=True)
    doTri = cmds.checkBox("mokaRT_doTri", q=True, v=True)

    doFlip = cmds.checkBox("mokaRT_doFlip", q=True, v=True)
    flipProb = cmds.floatField("mokaRT_flipProb", q=True, v=True)
    flipIter = cmds.intField("mokaRT_flipIter", q=True, v=True)

    keepHist = cmds.checkBox("mokaRT_keepHist", q=True, v=True)
    useOS = cmds.checkBox("mokaRT_useOS", q=True, v=True)

    random_triangulate_with_options(
        jitter_amount=jitter,
        seed=seed,
        lock_axes=(lockX, lockY, lockZ),
        lock_boundary=lockBoundary,
        do_triangulate=doTri,
        do_flip=doFlip,
        flip_probability=flipProb,
        flip_iterations=flipIter,
        keep_history=keepHist,
        use_object_space=useOS
    )

def _ui_on_toggle_flip(*_):
    doFlip = cmds.checkBox("mokaRT_doFlip", q=True, v=True)
    cmds.floatField("mokaRT_flipProb", e=True, en=doFlip)
    cmds.intField("mokaRT_flipIter", e=True, en=doFlip)

def show_random_triangulate_ui():
    if cmds.window(WIN_NAME, exists=True):
        cmds.deleteUI(WIN_NAME)

    cmds.window(WIN_NAME, title="Random Triangulate (Axis Lock)", sizeable=False)
    cmds.columnLayout(adjustableColumn=True, rowSpacing=8, columnAlign="left")

    cmds.frameLayout(label="Vertex Randomize", collapsable=False, marginWidth=10, marginHeight=8)
    cmds.columnLayout(adjustableColumn=True, rowSpacing=6)

    cmds.rowLayout(numberOfColumns=2, columnWidth2=(170, 140), adjustableColumn=2)
    cmds.text(label="Jitter Amount")
    cmds.floatField("mokaRT_jitter", v=0.02, minValue=0.0)
    cmds.setParent("..")

    cmds.rowLayout(numberOfColumns=2, columnWidth2=(170, 140), adjustableColumn=2)
    cmds.text(label="Seed (same result)")
    cmds.intField("mokaRT_seed", v=1)
    cmds.setParent("..")

    cmds.text(label="Lock Axis (checked = do NOT move)")
    cmds.rowLayout(numberOfColumns=3, columnWidth3=(100, 100, 100))
    cmds.checkBox("mokaRT_lockX", label="Lock X", v=False)
    cmds.checkBox("mokaRT_lockY", label="Lock Y", v=True)
    cmds.checkBox("mokaRT_lockZ", label="Lock Z", v=False)
    cmds.setParent("..")

    cmds.checkBox("mokaRT_lockBoundary", label="Lock Boundary (keep silhouette)", v=True)
    cmds.checkBox("mokaRT_useOS", label="Use Object Space (if rotated plane)", v=False)

    cmds.setParent("..")
    cmds.setParent("..")

    cmds.frameLayout(label="Triangulate / Random Flip", collapsable=False, marginWidth=10, marginHeight=8)
    cmds.columnLayout(adjustableColumn=True, rowSpacing=6)

    cmds.checkBox("mokaRT_doTri", label="Triangulate", v=True)

    cmds.checkBox("mokaRT_doFlip", label="Random Flip Edges (optional)", v=False, cc=_ui_on_toggle_flip)
    cmds.rowLayout(numberOfColumns=2, columnWidth2=(170, 140), adjustableColumn=2)
    cmds.text(label="Flip Probability")
    cmds.floatField("mokaRT_flipProb", v=0.8, minValue=0.0, maxValue=1.0, en=False)
    cmds.setParent("..")
    cmds.rowLayout(numberOfColumns=2, columnWidth2=(170, 140), adjustableColumn=2)
    cmds.text(label="Flip Iterations")
    cmds.intField("mokaRT_flipIter", v=3, minValue=1, en=False)
    cmds.setParent("..")

    cmds.checkBox("mokaRT_keepHist", label="Keep History", v=True)

    cmds.setParent("..")
    cmds.setParent("..")

    cmds.separator(h=8, style="in")

    cmds.rowLayout(numberOfColumns=2, columnWidth2=(155, 155))
    cmds.button(label="Run on Selected", h=32, c=_ui_on_run)
    cmds.button(label="Close", h=32, c=lambda *_: cmds.deleteUI(WIN_NAME))
    cmds.setParent("..")

    cmds.showWindow(WIN_NAME)

# これを実行するとUIが出る
show_random_triangulate_ui()
