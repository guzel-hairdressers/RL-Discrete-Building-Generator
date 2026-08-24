import * as THREE from '/vendor/three/build/three.module.js';
import { OrbitControls } from '/vendor/three/examples/jsm/controls/OrbitControls.js';

export function initUrbanContext(DATA) {
  // --- Scene Setup ---
  const scene = new THREE.Scene();
  window.scene = scene;
  window.THREE = THREE;

  // Global Optimizer Placements Group
  const optimizerGroup = new THREE.Group();
  optimizerGroup.name = "optimizerGroup";
  scene.add(optimizerGroup);
  window.optimizerGroup = optimizerGroup;

  // Ambient and Fill Lighting for Architectural Module Visibility
  if (!window._moduleLabLightsAdded) {
    window._moduleLabLightsAdded = true;
    const ambLight = new THREE.AmbientLight(0xffffff, 0.95);
    scene.add(ambLight);
    const fillLight = new THREE.DirectionalLight(0xffffff, 0.50);
    fillLight.position.set(-120, 160, -100);
    scene.add(fillLight);
  }

  // Handle Optimizer Placements Message
  window.addEventListener('message', (event) => {
    if (!event.data) return;
    
    if (event.data.type === 'set_context_visibility') {
      const isVisible = event.data.visible !== false;
      scene.traverse((obj) => {
        if (obj.name && (obj.name.toLowerCase().includes('context') || obj.name.toLowerCase().includes('surround'))) {
          obj.visible = isVisible;
        }
      });
      return;
    }

    if (event.data.type === 'set_camera_mode' && event.data.mode) {
      setCamera(event.data.mode === 'axonometric' ? 'ortho' : 'persp');
      return;
    }

    if (event.data.type !== 'optimizer_placements') return;
    const { placements, boundaries } = event.data;
    while (optimizerGroup.children.length > 0) {
      const child = optimizerGroup.children.pop();
      if (child.geometry) child.geometry.dispose();
    }
    if (!Array.isArray(placements) || placements.length === 0) return;

    const floorHeight = 3.5;
    const theme = event.data.colorTheme || {};

    const coreLitColor = new THREE.Color(theme.core || '#ffcccc');
    const coreShadowColor = new THREE.Color(theme.coreShadow || '#ff9999');
    const roomLitColor = new THREE.Color(theme.room || '#ffffff');
    const roomShadowColor = new THREE.Color(theme.roomShadow || '#e2e8f0');
    const edgeHex = theme.edge ? (typeof theme.edge === 'string' ? parseInt(theme.edge.replace('#', '0x')) : theme.edge) : 0x000000;
    const edgeMat = new THREE.LineBasicMaterial({ color: edgeHex, linewidth: 3.5 });

    const sunDir = (typeof sunVector !== 'undefined') ? sunVector : new THREE.Vector3(130, 220, 90).normalize();

    placements.forEach((placement) => {
      const floorIdx = Number(placement.instanceIdx ?? placement.floorIndex ?? 0);
      const poly = placement.poly || placement.polygon || placement.mergedPolygon || placement.coords;
      if (!Array.isArray(poly) || poly.length < 3) return;

      const floorBoundary = (Array.isArray(boundaries) && (boundaries.find((b) => Number(b.instanceIdx) === floorIdx) || boundaries[floorIdx])) || { offset: { x: 0, y: 0 }, originOffset: { x: 0, y: 0 } };
      const dx = Number(floorBoundary?.offset?.x || 0);
      const dy = Number(floorBoundary?.offset?.y || 0);
      const ox = Number(floorBoundary?.originOffset?.x || 0);
      const oy = Number(floorBoundary?.originOffset?.y || 0);

      const comps = (Array.isArray(placement.components) && placement.components.length > 1)
        ? placement.components
        : [placement];

      comps.forEach((comp) => {
        const cPoly = comp.poly || comp.polygon || comp.coords;
        if (!Array.isArray(cPoly) || cPoly.length < 3) return;

        const cShape = new THREE.Shape();
        cPoly.forEach((p, idx) => {
          const px = Number(p.x ?? p[0] ?? 0);
          const py = Number(p.y ?? p[1] ?? 0);
          const localX = px - dx;
          const localY = py - dy;
          const x3d = localX + ox;
          const y3d = localY + oy;
          if (idx === 0) cShape.moveTo(x3d, y3d);
          else cShape.lineTo(x3d, y3d);
        });

        const cGeom = new THREE.ExtrudeGeometry(cShape, {
          depth: floorHeight - 0.15,
          bevelEnabled: true,
          bevelSize: 0.04,
          bevelThickness: 0.04,
        });
        cGeom.rotateX(-Math.PI / 2);
        cGeom.translate(0, floorIdx * floorHeight + 0.2, 0);

        const cCat = comp.category || (comp.module ? comp.module.category : 'room');
        const isCore = cCat === 'core' || comp.isCore || (comp.id && String(comp.id).toLowerCase().includes('core'));
        const litColor = isCore ? coreLitColor : roomLitColor;
        const shadowColor = isCore ? coreShadowColor : roomShadowColor;

        const nonIndexed = cGeom.toNonIndexed();
        const posAttr = nonIndexed.attributes.position;
        const vertexCount = posAttr.count;
        const numTris = vertexCount / 3;
        const colors = new Float32Array(vertexCount * 3);

        for (let ti = 0; ti < numTris; ti++) {
          const idx0 = ti * 3;
          const idx1 = ti * 3 + 1;
          const idx2 = ti * 3 + 2;

          const p0 = new THREE.Vector3(posAttr.getX(idx0), posAttr.getY(idx0), posAttr.getZ(idx0));
          const p1 = new THREE.Vector3(posAttr.getX(idx1), posAttr.getY(idx1), posAttr.getZ(idx1));
          const p2 = new THREE.Vector3(posAttr.getX(idx2), posAttr.getY(idx2), posAttr.getZ(idx2));

          const vA = new THREE.Vector3().subVectors(p1, p0);
          const vB = new THREE.Vector3().subVectors(p2, p0);
          const faceNormal = new THREE.Vector3().crossVectors(vA, vB).normalize();

          const dot = faceNormal.dot(sunDir);
          const isSunFacing = dot > 0.05;
          const c = isSunFacing ? litColor : shadowColor;

          colors[idx0 * 3 + 0] = c.r;
          colors[idx0 * 3 + 1] = c.g;
          colors[idx0 * 3 + 2] = c.b;

          colors[idx1 * 3 + 0] = c.r;
          colors[idx1 * 3 + 1] = c.g;
          colors[idx1 * 3 + 2] = c.b;

          colors[idx2 * 3 + 0] = c.r;
          colors[idx2 * 3 + 1] = c.g;
          colors[idx2 * 3 + 2] = c.b;
        }

        nonIndexed.setAttribute('color', new THREE.BufferAttribute(colors, 3));
        nonIndexed.computeVertexNormals();

        const baseMat = new THREE.MeshBasicMaterial({ vertexColors: true });
        const mesh = new THREE.Mesh(nonIndexed, baseMat);

        const casterMat = new THREE.MeshBasicMaterial({ colorWrite: false });
        const casterMesh = new THREE.Mesh(nonIndexed, casterMat);
        casterMesh.castShadow = true;
        mesh.add(casterMesh);

        optimizerGroup.add(mesh);
      });

      // Solid black multi-pass outline around the outer merged macro-polygon
      const outerShape = new THREE.Shape();
      poly.forEach((p, idx) => {
        const px = Number(p.x ?? p[0] ?? 0);
        const py = Number(p.y ?? p[1] ?? 0);
        const localX = px - dx;
        const localY = py - dy;
        const x3d = localX + ox;
        const y3d = localY + oy;
        if (idx === 0) outerShape.moveTo(x3d, y3d);
        else outerShape.lineTo(x3d, y3d);
      });

      const outerGeom = new THREE.ExtrudeGeometry(outerShape, {
        depth: floorHeight - 0.15,
        bevelEnabled: true,
        bevelSize: 0.04,
        bevelThickness: 0.04,
      });
      outerGeom.rotateX(-Math.PI / 2);
      outerGeom.translate(0, floorIdx * floorHeight + 0.2, 0);

      const edges = new THREE.EdgesGeometry(outerGeom, 15);
      const edgeOffsets = [
        [0, 0, 0],
        [0.055, 0, 0], [-0.055, 0, 0],
        [0.055, 0, 0], [-0.055, 0, 0],
        [0, 0, 0.055], [0, 0, -0.055],
        [0.04, 0.04, 0.04], [-0.04, -0.04, -0.04],
        [0.04, -0.04, 0.04], [-0.04, 0.04, -0.04],
        [0.04, 0.04, -0.04], [-0.04, -0.04, 0.04]
      ];
      edgeOffsets.forEach(([ox, oy, oz]) => {
        const line = new THREE.LineSegments(edges, edgeMat);
        line.position.set(ox, oy, oz);
        optimizerGroup.add(line);
      });
    });
  });

  scene.background = new THREE.Color(0xffffff);

  const aspect = window.innerWidth / window.innerHeight;
  const R = DATA.radius || 150;

  // Orthographic Camera (Axonometric) - DEFAULT
  const orthoSize = R * 1.45;
  const cameraOrtho = new THREE.OrthographicCamera(
    -orthoSize * aspect, orthoSize * aspect,
    orthoSize, -orthoSize,
    1, 3000
  );
  const camDist = R * 2.8;
  cameraOrtho.position.set(camDist * 0.7, camDist * 0.65, camDist * 0.7);

  // Perspective Camera
  const cameraPersp = new THREE.PerspectiveCamera(38, aspect, 1, 3000);
  cameraPersp.position.set(camDist * 0.7, camDist * 0.65, camDist * 0.7);

  let activeCamera = cameraOrtho;

  // Renderer
  const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
  renderer.setSize(window.innerWidth, window.innerHeight);
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
  renderer.toneMapping = THREE.NoToneMapping;
  renderer.shadowMap.enabled = true;
  renderer.shadowMap.type = THREE.PCFSoftShadowMap;
  document.body.appendChild(renderer.domElement);

  // Controls
  const controls = new OrbitControls(activeCamera, renderer.domElement);
  controls.enableDamping = true;
  controls.dampingFactor = 0.18;
  controls.maxPolarAngle = Math.PI / 2.0;
  controls.target.set(0, (DATA.maxHeight || 40) * 0.08, 0);

  // Load Saved Camera State if available
  try {
    const savedState = localStorage.getItem('context_generator_camera_view');
    if (savedState) {
      const view = JSON.parse(savedState);
      if (view && view.pos && view.target) {
        cameraOrtho.position.set(view.pos[0], view.pos[1], view.pos[2]);
        cameraPersp.position.set(view.pos[0], view.pos[1], view.pos[2]);
        controls.target.set(view.target[0], view.target[1], view.target[2]);
      }
    }
  } catch (e) {}

  controls.addEventListener('end', () => {
    try {
      localStorage.setItem('context_generator_camera_view', JSON.stringify({
        pos: [activeCamera.position.x, activeCamera.position.y, activeCamera.position.z],
        target: [controls.target.x, controls.target.y, controls.target.z],
      }));
    } catch (e) {}
  });

  // Lighting
  const sunElevation = THREE.MathUtils.degToRad(DATA.sun?.elevation || 45);
  const sunAzimuth = THREE.MathUtils.degToRad(DATA.sun?.azimuth || 135);
  const sunVector = new THREE.Vector3(
    Math.cos(sunElevation) * Math.sin(sunAzimuth),
    Math.sin(sunElevation),
    Math.cos(sunElevation) * Math.cos(sunAzimuth)
  ).normalize();

  const dirLight = new THREE.DirectionalLight(0xffffff, 1.25);
  dirLight.position.copy(sunVector).multiplyScalar(400);
  dirLight.castShadow = true;
  dirLight.shadow.mapSize.width = 2048;
  dirLight.shadow.mapSize.height = 2048;
  const shadowRange = R * 1.5;
  dirLight.shadow.camera.left = -shadowRange;
  dirLight.shadow.camera.right = shadowRange;
  dirLight.shadow.camera.top = shadowRange;
  dirLight.shadow.camera.bottom = -shadowRange;
  dirLight.shadow.camera.near = 10;
  dirLight.shadow.camera.far = 1000;
  dirLight.shadow.bias = -0.00035;
  scene.add(dirLight);

  // Ground Plane
  const groundGeom = new THREE.PlaneGeometry(R * 8, R * 8);
  const groundMat = new THREE.ShadowMaterial({ opacity: 0.16 });
  const groundMesh = new THREE.Mesh(groundGeom, groundMat);
  groundMesh.rotation.x = -Math.PI / 2;
  groundMesh.position.y = -0.05;
  groundMesh.receiveShadow = true;
  scene.add(groundMesh);

  // Surrounding Buildings and Site Setup
  const interactiveObjects = [];
  const edgeLineMat = new THREE.LineBasicMaterial({ color: 0x000000, linewidth: 1.5 });

  if (DATA.buildings && Array.isArray(DATA.buildings)) {
    const contextGroup = new THREE.Group();
    contextGroup.name = "surroundingContext";

    DATA.buildings.forEach((bldg) => {
      if (!bldg.polygon || bldg.polygon.length < 3) return;
      const shape = new THREE.Shape();
      bldg.polygon.forEach((p, i) => {
        if (i === 0) shape.moveTo(p[0], -p[1]);
        else shape.lineTo(p[0], -p[1]);
      });

      const height = bldg.height || 12;
      const bGeom = new THREE.ExtrudeGeometry(shape, {
        depth: height,
        bevelEnabled: false,
      });
      bGeom.rotateX(-Math.PI / 2);

      const bMat = new THREE.MeshLambertMaterial({
        color: 0xf8fafc,
        emissive: 0x1e293b,
        emissiveIntensity: 0.05,
      });

      const bMesh = new THREE.Mesh(bGeom, bMat);
      bMesh.castShadow = true;
      bMesh.receiveShadow = true;
      bMesh.userData = {
        isBuilding: true,
        height: height,
        floors: bldg.floors || Math.round(height / 3.5),
        area: bldg.area || 0,
        use: bldg.use || 'Commercial / Residential',
      };
      contextGroup.add(bMesh);
      interactiveObjects.push(bMesh);

      // Building Outline
      const bEdges = new THREE.EdgesGeometry(bGeom, 25);
      const bLine = new THREE.LineSegments(bEdges, edgeLineMat);
      contextGroup.add(bLine);
    });

    scene.add(contextGroup);
  }

  // Testing Site Parcel
  if (DATA.site) {
    const siteGroup = new THREE.Group();
    const siteFaceColor = 0xfca5a5;

    const geom = new THREE.BufferGeometry();
    const pos = new Float32Array(DATA.site.faces.length * 9);
    for (let fi = 0; fi < DATA.site.faces.length; fi++) {
      const f = DATA.site.faces[fi];
      for (let vi = 0; vi < 3; vi++) {
        const v = DATA.site.vertices[f[vi]];
        pos[fi * 9 + vi * 3 + 0] = v[0];
        pos[fi * 9 + vi * 3 + 1] = v[2];
        pos[fi * 9 + vi * 3 + 2] = -v[1];
      }
    }
    geom.setAttribute('position', new THREE.BufferAttribute(pos, 3));
    geom.computeVertexNormals();

    const baseMat = new THREE.MeshLambertMaterial({
      color: new THREE.Color(siteFaceColor),
      emissive: new THREE.Color(siteFaceColor).multiplyScalar(0.55),
      transparent: true,
      opacity: 0.92,
    });
    const baseMesh = new THREE.Mesh(geom, baseMat);
    baseMesh.receiveShadow = true;
    baseMesh.userData = {
      isSite: true,
      area: DATA.siteArea,
      tier: DATA.areaTier,
      far: DATA.metrics?.far,
      bldgs: DATA.metrics?.buildingCount,
      maxHeight: DATA.metrics?.maxHeight,
      avgHeight: DATA.metrics?.avgHeight,
      maxFloors: DATA.metrics?.maxFloors,
      avgFloors: DATA.metrics?.avgFloors,
    };
    siteGroup.add(baseMesh);
    interactiveObjects.push(baseMesh);

    // Site Perimeter Boundary Line (Red)
    if (DATA.sitePerimeter && DATA.sitePerimeter.length >= 3) {
      const outPts = DATA.sitePerimeter.map((p) => new THREE.Vector3(p[0], 0.26, -p[1]));
      outPts.push(outPts[0].clone());
      const siteLineGeom = new THREE.BufferGeometry().setFromPoints(outPts);
      const siteLineMat = new THREE.LineBasicMaterial({ color: 0xef4444, linewidth: 2.5 });
      siteGroup.add(new THREE.Line(siteLineGeom, siteLineMat));
    }

    scene.add(siteGroup);
  }

  // --- Smooth Camera View Snap Function ---
  let isAnimatingCamera = false;
  let animStartTime = 0;
  let animStartPos = new THREE.Vector3();
  let animEndPos = new THREE.Vector3();
  const ANIM_DURATION = 350;

  function snapToView(dirX, dirY, dirZ) {
    const target = controls.target.clone();
    animStartPos.copy(activeCamera.position);

    cameraOrtho.up.set(0, 1, 0);
    cameraPersp.up.set(0, 1, 0);

    if (dirY === 1) {
      const dx = animStartPos.x - target.x;
      const dz = animStartPos.z - target.z;
      const dist2d = Math.hypot(dx, dz);
      const angle = dist2d > 0.001 ? Math.atan2(dx, dz) : 0;
      const eps = 0.001 * camDist;
      animEndPos.set(target.x + eps * Math.sin(angle), target.y + camDist, target.z + eps * Math.cos(angle));
    } else if (dirY === -1) {
      const dx = animStartPos.x - target.x;
      const dz = animStartPos.z - target.z;
      const dist2d = Math.hypot(dx, dz);
      const angle = dist2d > 0.001 ? Math.atan2(dx, dz) : 0;
      const eps = 0.001 * camDist;
      animEndPos.set(target.x + eps * Math.sin(angle), target.y - camDist, target.z + eps * Math.cos(angle));
    } else if (dirX === 1) {
      animEndPos.set(target.x + camDist, target.y, target.z);
    } else if (dirX === -1) {
      animEndPos.set(target.x - camDist, target.y, target.z);
    } else if (dirZ === 1) {
      animEndPos.set(target.x, target.y, target.z + camDist);
    } else if (dirZ === -1) {
      animEndPos.set(target.x, target.y, target.z - camDist);
    }

    animStartTime = performance.now();
    isAnimatingCamera = true;
  }

  // --- Blender Orientation Gizmo Widget ---
  const gizmoContainer = document.getElementById('gizmo-container');
  let gctx = null;
  let gizmoRenderNodes = [];
  const AXES = [
    { label: 'X', dir: [1, 0, 0], color: '#ef4444', isNeg: false },
    { label: 'Y', dir: [0, 0, 1], color: '#22c55e', isNeg: false },
    { label: 'Z', dir: [0, 1, 0], color: '#3b82f6', isNeg: false },
    { label: '-X', dir: [-1, 0, 0], color: '#ef4444', isNeg: true },
    { label: '-Y', dir: [0, 0, -1], color: '#22c55e', isNeg: true },
    { label: '-Z', dir: [0, -1, 0], color: '#3b82f6', isNeg: true },
  ];

  if (gizmoContainer) {
    const gizmoCanvas = document.createElement('canvas');
    gizmoCanvas.width = 240;
    gizmoCanvas.height = 240;
    gizmoCanvas.style.width = '120px';
    gizmoCanvas.style.height = '120px';
    gizmoContainer.appendChild(gizmoCanvas);
    gctx = gizmoCanvas.getContext('2d');

    gizmoCanvas.addEventListener('click', (e) => {
      const rect = gizmoCanvas.getBoundingClientRect();
      const mx = (e.clientX - rect.left) * 2;
      const my = (e.clientY - rect.top) * 2;
      const clickable = [...gizmoRenderNodes].reverse();
      for (const node of clickable) {
        const dist = Math.hypot(mx - node.px, my - node.py);
        const radius = node.isNeg ? 12 : 18;
        if (dist <= radius) {
          snapToView(node.dir[0], node.dir[1], node.dir[2]);
          break;
        }
      }
    });
  }

  function drawGizmo() {
    if (!gctx) return;
    gctx.clearRect(0, 0, 240, 240);
    const cx = 120, cy = 120, r = 75;
    const mat = new THREE.Matrix4();
    mat.extractRotation(activeCamera.matrixWorldInverse);

    const projected = AXES.map((axis) => {
      const vec = new THREE.Vector3(...axis.dir).applyMatrix4(mat);
      return {
        ...axis,
        px: cx + vec.x * r,
        py: cy - vec.y * r,
        pz: vec.z,
      };
    });

    projected.sort((a, b) => a.pz - b.pz);
    gizmoRenderNodes = projected;

    for (const node of projected) {
      gctx.beginPath();
      gctx.moveTo(cx, cy);
      gctx.lineTo(node.px, node.py);
      gctx.strokeStyle = node.isNeg ? '#cbd5e1' : node.color;
      gctx.lineWidth = node.isNeg ? 2 : 4;
      gctx.stroke();
    }

    for (const node of projected) {
      gctx.beginPath();
      const radius = node.isNeg ? 10 : 16;
      gctx.arc(node.px, node.py, radius, 0, Math.PI * 2);
      if (node.isNeg) {
        gctx.fillStyle = '#ffffff';
        gctx.fill();
        gctx.strokeStyle = node.color;
        gctx.lineWidth = 3;
        gctx.stroke();
      } else {
        gctx.fillStyle = node.color;
        gctx.fill();
        gctx.font = 'bold 18px Inter, sans-serif';
        gctx.textAlign = 'center';
        gctx.textBaseline = 'middle';
        gctx.fillStyle = '#ffffff';
        gctx.fillText(node.label, node.px, node.py + 1);
      }
    }
  }

  // Camera Switch Function
  function setCamera(cameraMode) {
    const prevCam = activeCamera;
    if (cameraMode === 'ortho') {
      activeCamera = cameraOrtho;
    } else {
      activeCamera = cameraPersp;
    }
    activeCamera.position.copy(prevCam.position);
    controls.object = activeCamera;
    controls.update();
  }

  // Hover Tooltips
  const raycaster = new THREE.Raycaster();
  const mouse = new THREE.Vector2();
  const tooltip = document.getElementById('tooltip');
  let hoveredObj = null;

  renderer.domElement.addEventListener('mousemove', (e) => {
    mouse.x = (e.clientX / window.innerWidth) * 2 - 1;
    mouse.y = -(e.clientY / window.innerHeight) * 2 + 1;
    raycaster.setFromCamera(mouse, activeCamera);
    const hits = raycaster.intersectObjects(interactiveObjects);

    if (hoveredObj) {
      hoveredObj.material.color.setHex(hoveredObj.userData.isSite ? 0xfca5a5 : 0xf8fafc);
      hoveredObj = null;
    }

    if (hits.length > 0) {
      const obj = hits[0].object;
      hoveredObj = obj;

      if (tooltip) {
        if (obj.userData.isSite) {
          obj.material.color.setHex(0xf87171);
          tooltip.style.display = 'block';
          tooltip.style.left = (e.clientX + 14) + 'px';
          tooltip.style.top = (e.clientY + 14) + 'px';
          tooltip.innerHTML = `
            <div style="font-weight:700; color:#0f172a; font-size:13px; margin-bottom:6px;">Testing Site Parcel</div>
            <div style="color:#334155; margin-bottom:3px;"><b style="color:#0f172a;">Site Area:</b> ${obj.userData.area || 0} m² (${obj.userData.tier || 'M'} Tier)</div>
            <div style="color:#334155; margin-bottom:3px;"><b style="color:#0f172a;">Context Height:</b> ${obj.userData.avgHeight || 15}m | ${obj.userData.maxHeight || 30}m</div>
            <div style="color:#334155;"><b style="color:#0f172a;">Context Storeys:</b> ${obj.userData.avgFloors || 5} | ${obj.userData.maxFloors || 10}</div>
          `;
        } else if (obj.userData.isBuilding) {
          obj.material.color.setHex(0xdbeafe);
          tooltip.style.display = 'block';
          tooltip.style.left = (e.clientX + 14) + 'px';
          tooltip.style.top = (e.clientY + 14) + 'px';
          tooltip.innerHTML = `
            <div style="font-weight:700; color:#0f172a; font-size:13px; margin-bottom:6px;">${obj.userData.use || 'Building'}</div>
            <div style="color:#334155; margin-bottom:3px;"><b style="color:#0f172a;">Footprint:</b> ${obj.userData.area || 0} m²</div>
            <div style="color:#334155; margin-bottom:3px;"><b style="color:#0f172a;">Height:</b> ${obj.userData.height || 0} m</div>
            <div style="color:#334155;"><b style="color:#0f172a;">Storeys:</b> ${obj.userData.floors || 0}</div>
          `;
        }
      }
    } else if (tooltip) {
      tooltip.style.display = 'none';
    }
  });

  // Resize Handler
  window.addEventListener('resize', () => {
    const newAspect = window.innerWidth / window.innerHeight;
    cameraPersp.aspect = newAspect;
    cameraPersp.updateProjectionMatrix();

    cameraOrtho.left = -orthoSize * newAspect;
    cameraOrtho.right = orthoSize * newAspect;
    cameraOrtho.top = orthoSize;
    cameraOrtho.bottom = -orthoSize;
    cameraOrtho.updateProjectionMatrix();

    renderer.setSize(window.innerWidth, window.innerHeight);
  });

  // Animation Loop
  function animate() {
    requestAnimationFrame(animate);

    if (isAnimatingCamera) {
      const now = performance.now();
      const progress = Math.min(1.0, (now - animStartTime) / ANIM_DURATION);
      const easeProgress = 1 - Math.pow(1 - progress, 3);

      controls.enabled = false;
      activeCamera.position.lerpVectors(animStartPos, animEndPos, easeProgress);
      activeCamera.lookAt(controls.target);

      if (progress >= 1.0) {
        isAnimatingCamera = false;
        controls.enabled = true;
        controls.update();
      }
    } else {
      controls.update();
    }

    renderer.render(scene, activeCamera);
    drawGizmo();
  }

  animate();

  // Notify parent window that 3D viewer is loaded and ready
  try {
    window.parent.postMessage({ type: 'viewer_ready' }, '*');
  } catch (e) {}
}
