import React, { forwardRef, useEffect, useImperativeHandle, useRef, useState } from "react";
import * as THREE from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";
import { STLLoader } from "three/examples/jsm/loaders/STLLoader.js";
import { CSS2DRenderer, CSS2DObject } from "three/examples/jsm/renderers/CSS2DRenderer.js";
import { Loader2 } from "lucide-react";

const VIEW_DIRS = {
  iso: [-1, -1.2, 0.9],
  front: [0, -1, 0.0001],
  back: [0, 1, 0.0001],
  right: [1, 0, 0.0001],
  left: [-1, 0, 0.0001],
  top: [0, -0.0001, 1],
  bottom: [0, -0.0001, -1],
};

const Viewer3D = forwardRef(function Viewer3D({ url, points, pickMode, onPick, wireframe }, ref) {
  const mountRef = useRef(null);
  const S = useRef({});
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const pickRef = useRef({ pickMode, onPick });
  pickRef.current = { pickMode, onPick };

  const fit = (dirName = "iso") => {
    const s = S.current;
    if (!s.box) return;
    const center = s.box.getCenter(new THREE.Vector3());
    const R = s.box.getSize(new THREE.Vector3()).length() / 2 || 10;
    const dir = new THREE.Vector3(...VIEW_DIRS[dirName]).normalize();
    s.camera.position.copy(center.clone().add(dir.multiplyScalar(R * 2.6)));
    s.camera.near = R / 200;
    s.camera.far = R * 200;
    s.camera.updateProjectionMatrix();
    s.controls.target.copy(center);
    s.controls.update();
  };

  useImperativeHandle(ref, () => ({ setView: fit }));

  // init scene
  useEffect(() => {
    const el = mountRef.current;
    const s = S.current;
    const scene = new THREE.Scene();
    scene.background = new THREE.Color("#101317");
    const camera = new THREE.PerspectiveCamera(40, el.clientWidth / el.clientHeight, 0.1, 10000);
    camera.up.set(0, 0, 1);
    camera.position.set(-100, -120, 90);
    const renderer = new THREE.WebGLRenderer({ antialias: true, preserveDrawingBuffer: true });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.setSize(el.clientWidth, el.clientHeight);
    el.appendChild(renderer.domElement);
    const labels = new CSS2DRenderer();
    labels.setSize(el.clientWidth, el.clientHeight);
    labels.domElement.className = "viewer-labels";
    el.appendChild(labels.domElement);

    scene.add(new THREE.HemisphereLight(0xdfe8ff, 0x1a1d22, 1.1));
    const d1 = new THREE.DirectionalLight(0xffffff, 1.6);
    d1.position.set(-1, -2, 3);
    scene.add(d1);
    const d2 = new THREE.DirectionalLight(0xffd2b0, 0.6);
    d2.position.set(2, 1, -1);
    scene.add(d2);
    scene.add(new THREE.AmbientLight(0xffffff, 0.15));

    const controls = new OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;
    controls.dampingFactor = 0.12;

    const markers = new THREE.Group();
    scene.add(markers);
    Object.assign(s, { scene, camera, renderer, labels, controls, markers });

    let raf;
    const loop = () => {
      controls.update();
      renderer.render(scene, camera);
      labels.render(scene, camera);
      raf = requestAnimationFrame(loop);
    };
    loop();

    const ro = new ResizeObserver(() => {
      const w = el.clientWidth, h = el.clientHeight;
      if (!w || !h) return;
      camera.aspect = w / h;
      camera.updateProjectionMatrix();
      renderer.setSize(w, h);
      labels.setSize(w, h);
    });
    ro.observe(el);

    // click vs drag detection for picking
    let down = null;
    const onDown = (e) => (down = { x: e.clientX, y: e.clientY });
    const onUp = (e) => {
      if (!down) return;
      const moved = Math.hypot(e.clientX - down.x, e.clientY - down.y);
      down = null;
      const { pickMode: pm, onPick: op } = pickRef.current;
      if (!pm || moved > 5 || !s.mesh) return;
      const rect = renderer.domElement.getBoundingClientRect();
      const ndc = new THREE.Vector2(((e.clientX - rect.left) / rect.width) * 2 - 1, -((e.clientY - rect.top) / rect.height) * 2 + 1);
      const rc = new THREE.Raycaster();
      rc.setFromCamera(ndc, camera);
      const hit = rc.intersectObject(s.mesh, false)[0];
      if (hit && op) op([hit.point.x, hit.point.y, hit.point.z].map((v) => Math.round(v * 1000) / 1000));
    };
    renderer.domElement.addEventListener("pointerdown", onDown);
    renderer.domElement.addEventListener("pointerup", onUp);

    return () => {
      cancelAnimationFrame(raf);
      ro.disconnect();
      renderer.domElement.removeEventListener("pointerdown", onDown);
      renderer.domElement.removeEventListener("pointerup", onUp);
      controls.dispose();
      renderer.dispose();
      el.innerHTML = "";
    };
  }, []);

  // load STL
  useEffect(() => {
    const s = S.current;
    if (!url || !s.scene) return;
    let cancelled = false;
    setLoading(true);
    setError(null);
    fetch(url)
      .then((r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.arrayBuffer();
      })
      .then((buf) => {
        if (cancelled) return;
        const geom = new STLLoader().parse(buf);
        geom.computeVertexNormals();
        geom.computeBoundingBox();
        const firstLoad = !s.mesh;
        if (s.mesh) {
          s.scene.remove(s.mesh);
          s.mesh.geometry.dispose();
        }
        if (s.edges) {
          s.scene.remove(s.edges);
          s.edges.geometry.dispose();
        }
        if (s.grid) s.scene.remove(s.grid);
        const mat = new THREE.MeshStandardMaterial({ color: 0xb9c3d1, metalness: 0.05, roughness: 0.55, flatShading: false });
        const mesh = new THREE.Mesh(geom, mat);
        s.scene.add(mesh);
        const edges = new THREE.LineSegments(new THREE.EdgesGeometry(geom, 30), new THREE.LineBasicMaterial({ color: 0x3a4250 }));
        s.scene.add(edges);
        const box = geom.boundingBox.clone();
        const size = box.getSize(new THREE.Vector3());
        const gsize = Math.ceil((Math.max(size.x, size.y) * 1.6) / 10) * 10 || 100;
        const grid = new THREE.GridHelper(gsize, gsize / 5, 0x2f3540, 0x1d2128);
        grid.rotation.x = Math.PI / 2;
        const c = box.getCenter(new THREE.Vector3());
        grid.position.set(c.x, c.y, box.min.z - 0.01);
        s.scene.add(grid);
        Object.assign(s, { mesh, edges, grid, box });
        const prevBox = s.prevBoxKey;
        const key = [size.x, size.y, size.z].map((v) => v.toFixed(1)).join(",");
        if (firstLoad || prevBox !== key) fit("iso");
        s.prevBoxKey = key;
        applyWire();
        setLoading(false);
      })
      .catch((e) => {
        if (!cancelled) {
          setError(e.message);
          setLoading(false);
        }
      });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [url]);

  const applyWire = () => {
    const s = S.current;
    if (s.mesh) s.mesh.material.wireframe = !!wireframe;
  };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(applyWire, [wireframe]);

  // markers
  useEffect(() => {
    const s = S.current;
    if (!s.markers) return;
    s.markers.children.slice().forEach((m) => {
      m.traverse((o) => {
        if (o.isCSS2DObject && o.element) o.element.remove();
      });
      s.markers.remove(m);
    });
    const R = s.box ? s.box.getSize(new THREE.Vector3()).length() / 2 : 30;
    (points || []).forEach((p, i) => {
      const g = new THREE.Mesh(
        new THREE.SphereGeometry(Math.max(0.4, R * 0.018), 20, 14),
        new THREE.MeshBasicMaterial({ color: 0xff6a1a, depthTest: false })
      );
      g.renderOrder = 10;
      g.position.set(...p.point);
      const div = document.createElement("div");
      div.className = "marker-label";
      div.textContent = `P${i + 1}`;
      const lbl = new CSS2DObject(div);
      lbl.position.set(0, 0, 0);
      lbl.center.set(-0.25, 1.2);
      g.add(lbl);
      s.markers.add(g);
    });
  }, [points, url]);

  return (
    <div className={`viewer ${pickMode ? "is-picking" : ""}`} data-testid="viewer-3d">
      <div ref={mountRef} className="viewer-canvas" />
      {loading && (
        <div className="viewer-overlay" data-testid="viewer-loading">
          <Loader2 className="spin" size={22} /> Chargement du modèle...
        </div>
      )}
      {error && <div className="viewer-overlay error">Impossible de charger le modèle : {error}</div>}
    </div>
  );
});

export default Viewer3D;
