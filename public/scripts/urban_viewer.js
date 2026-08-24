import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';

export function initUrbanContext(DATA) {
  // --- Scene Setup ---
  const scene = new THREE.Scene();
  scene.background = new THREE.Color(0xffffff); // Pure 100% white background
  window.scene = scene;
  window.THREE = THREE;

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

  let activeCamera = cameraOrtho; // DEFAULT AXONOMETRIC

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

  // Global Optimizer Placements Group
  const optimizerGroup = new THREE.Group();
  optimizerGroup.name = "optimizerGroup";
  scene.add(optimizerGroup);
  window.optimizerGroup = optimizerGroup;

  // Camera State Persistence
  try {
    const savedState = localStorage.getItem('context_generator_camera_view');
    if (savedState) {
      const view = JSON.parse(savedState);
      if (
        view &&
        view.pos &&
        Array.isArray(view.pos) &&
        !isNaN(view.pos[0]) &&
        !isNaN(view.pos[1]) &&
        !isNaN(view.pos[2]) &&
        (Math.abs(view.pos[0]) > 0.001 || Math.abs(view.pos[1]) > 0.001 || Math.abs(view.pos[2]) > 0.001) &&
        view.target &&
        Array.isArray(view.target) &&
        !isNaN(view.target[0]) &&
        !isNaN(view.target[1]) &&
        !isNaN(view.target[2])
      ) {
        cameraOrtho.position.set(view.pos[0], view.pos[1], view.pos[2]);
        cameraPersp.position.set(view.pos[0], view.pos[1], view.pos[2]);
        if (view.zoom && !isNaN(view.zoom)) cameraOrtho.zoom = view.zoom;
        cameraOrtho.updateProjectionMatrix();
        cameraPersp.updateProjectionMatrix();
        controls.target.set(view.target[0], view.target[1], view.target[2]);
        if (view.isPersp) {
          activeCamera = cameraPersp;
          controls.object = cameraPersp;
        }
      }
    }
  } catch (e) {}

  controls.addEventListener('change', () => {
    try {
      if (
        !isNaN(activeCamera.position.x) &&
        !isNaN(activeCamera.position.y) &&
        !isNaN(activeCamera.position.z) &&
        (Math.abs(activeCamera.position.x) > 0.001 || Math.abs(activeCamera.position.y) > 0.001 || Math.abs(activeCamera.position.z) > 0.001) &&
        !isNaN(controls.target.x) &&
        !isNaN(controls.target.y) &&
        !isNaN(controls.target.z)
      ) {
        const view = {
          pos: [activeCamera.position.x, activeCamera.position.y, activeCamera.position.z],
          target: [controls.target.x, controls.target.y, controls.target.z],
          zoom: cameraOrtho.zoom,
          isPersp: activeCamera === cameraPersp,
        };
        localStorage.setItem('context_generator_camera_view', JSON.stringify(view));
      }
    } catch (e) {}
  });

  // Sun Light & Vector
  const sunVector = new THREE.Vector3(130, 220, 90).normalize();
  const sunLight = new THREE.DirectionalLight(0xffffff, 1.0);
  sunLight.position.set(130, 220, 90);
  sunLight.castShadow = true;
  sunLight.shadow.mapSize.width = 2048;
  sunLight.shadow.mapSize.height = 2048;

  const shadowDim = R * 1.6;
  sunLight.shadow.camera.left = -shadowDim;
  sunLight.shadow.camera.right = shadowDim;
  sunLight.shadow.camera.top = shadowDim;
  sunLight.shadow.camera.bottom = -shadowDim;
  sunLight.shadow.camera.near = 10;
  sunLight.shadow.camera.far = 600;
  sunLight.shadow.bias = -0.0005;
  sunLight.shadow.normalBias = 0.05;
  scene.add(sunLight);

  // Ground Plane
  const groundGeom = new THREE.PlaneGeometry(R * 2, R * 2);
  const groundMat = new THREE.MeshBasicMaterial({ color: 0xffffff });
  const ground = new THREE.Mesh(groundGeom, groundMat);
  ground.rotation.x = -Math.PI / 2;
  ground.position.y = -0.05;
  scene.add(ground);

  // Shared Shadow Material Overlay
  const sharedShadowMat = new THREE.ShadowMaterial({
    color: 0x000000,
    opacity: 0.08,
    depthWrite: false,
    polygonOffset: true,
    polygonOffsetFactor: -1.0,
    polygonOffsetUnits: -1.0,
  });

  const shadowPlane = new THREE.Mesh(groundGeom, sharedShadowMat);
  shadowPlane.rotation.x = -Math.PI / 2;
  shadowPlane.position.y = -0.01;
  shadowPlane.receiveShadow = true;
  scene.add(shadowPlane);

  // Bounding box border line
  const borderPts = [
    new THREE.Vector3(-R, 0.1,  R),
    new THREE.Vector3( R, 0.1,  R),
    new THREE.Vector3( R, 0.1, -R),
    new THREE.Vector3(-R, 0.1, -R),
    new THREE.Vector3(-R, 0.1,  R),
  ];
  const borderGeom = new THREE.BufferGeometry().setFromPoints(borderPts);
  scene.add(new THREE.Line(borderGeom, new THREE.LineBasicMaterial({ color: 0xd1d5db, linewidth: 1.2 })));

  // Meter Scale Ticks
  function createTickLabel(text) {
    const canvas = document.createElement('canvas');
    const ctx = canvas.getContext('2d');
    canvas.width = 128; canvas.height = 64;
    ctx.font = '400 20px Inter, sans-serif';
    ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
    ctx.fillStyle = '#000000';
    ctx.fillText(text, 64, 32);
    const texture = new THREE.CanvasTexture(canvas);
    texture.minFilter = THREE.LinearFilter;
    const sprite = new THREE.Sprite(new THREE.SpriteMaterial({ map: texture, transparent: true }));
    sprite.scale.set(14, 7, 1);
    return sprite;
  }

  for (let val = -R; val <= R; val += 50) {
    const xFront = createTickLabel(`${val}m`);
    xFront.position.set(val, 0.5, R + 7);
    scene.add(xFront);

    const xBack = createTickLabel(`${val}m`);
    xBack.position.set(val, 0.5, -R - 7);
    scene.add(xBack);

    const zLeft = createTickLabel(`${val}m`);
    zLeft.position.set(-R - 7, 0.5, -val);
    scene.add(zLeft);

    const zRight = createTickLabel(`${val}m`);
    zRight.position.set(R + 7, 0.5, -val);
    scene.add(zRight);
  }

  // Architectural Volume Builder for Context Meshes (Buildings, Roads, Green Spaces)
  function createArchitecturalVolume(verts, faces, colorHex = 0xffffff, opacity = 1.0, isRoad = false) {
    const group = new THREE.Group();
    if (!verts || !faces || faces.length === 0) return { geom: new THREE.BufferGeometry(), baseMesh: new THREE.Mesh(), group };

    const numTriangles = faces.length;
    const pos = new Float32Array(numTriangles * 9);
    const colors = new Float32Array(numTriangles * 9);

    const pureColor = new THREE.Color(colorHex);
    const sunFacingPositions = [];

    for (let fi = 0; fi < numTriangles; fi++) {
      const f = faces[fi];
      const p0 = new THREE.Vector3(verts[f[0]][0], verts[f[0]][2], -verts[f[0]][1]);
      const p1 = new THREE.Vector3(verts[f[1]][0], verts[f[1]][2], -verts[f[1]][1]);
      const p2 = new THREE.Vector3(verts[f[2]][0], verts[f[2]][2], -verts[f[2]][1]);

      const vA = new THREE.Vector3().subVectors(p1, p0);
      const vB = new THREE.Vector3().subVectors(p2, p0);
      const faceNormal = new THREE.Vector3().crossVectors(vA, vB).normalize();

      const dot = faceNormal.dot(sunVector);
      const isSunFacing = (isRoad || dot > 0.05);
      const c = pureColor;

      for (let vi = 0; vi < 3; vi++) {
        const v = verts[f[vi]];
        pos[fi * 9 + vi * 3 + 0] = v[0];
        pos[fi * 9 + vi * 3 + 1] = v[2];
        pos[fi * 9 + vi * 3 + 2] = -v[1];

        colors[fi * 9 + vi * 3 + 0] = c.r;
        colors[fi * 9 + vi * 3 + 1] = c.g;
        colors[fi * 9 + vi * 3 + 2] = c.b;
      }

      if (isSunFacing && !isRoad) {
        for (let vi = 0; vi < 3; vi++) {
          const v = verts[f[vi]];
          sunFacingPositions.push(v[0], v[2], -v[1]);
        }
      }
    }

    const geom = new THREE.BufferGeometry();
    geom.setAttribute('position', new THREE.BufferAttribute(pos, 3));
    geom.setAttribute('color', new THREE.BufferAttribute(colors, 3));
    geom.computeVertexNormals();

    const baseMat = new THREE.MeshBasicMaterial({
      vertexColors: true,
      transparent: opacity < 1.0,
      opacity: opacity,
      polygonOffset: isRoad,
      polygonOffsetFactor: isRoad ? 2.0 : 0.0,
      polygonOffsetUnits: isRoad ? 2.0 : 0.0,
    });
    const baseMesh = new THREE.Mesh(geom, baseMat);
    group.add(baseMesh);

    if (!isRoad) {
      const casterMat = new THREE.MeshBasicMaterial({ colorWrite: false });
      const casterMesh = new THREE.Mesh(geom, casterMat);
      casterMesh.castShadow = true;
      group.add(casterMesh);

      if (sunFacingPositions.length > 0) {
        const sunGeom = new THREE.BufferGeometry();
        sunGeom.setAttribute('position', new THREE.Float32BufferAttribute(sunFacingPositions, 3));
        sunGeom.computeVertexNormals();

        const buildingShadowOverlay = new THREE.Mesh(sunGeom, sharedShadowMat);
        buildingShadowOverlay.receiveShadow = true;
        group.add(buildingShadowOverlay);
      }
    }

    return { geom, baseMesh, group };
  }

  // Surrounding Buildings and Context Setup
  const interactiveObjects = [];
  const contextGroup = new THREE.Group();
  contextGroup.name = "surroundingContext";

  if (DATA.buildings && Array.isArray(DATA.buildings)) {
    for (const b of DATA.buildings) {
      if (!b.vertices || !b.faces) continue;
      const faceColor = 0xffffff;
      const edgeColor = 0x999999;

      const { geom, baseMesh, group } = createArchitecturalVolume(b.vertices, b.faces, faceColor, 0.98, false);
      baseMesh.userData = {
        isBuilding: true,
        area: b.area || 0,
        height: b.height || 0,
        floors: b.floors || 0,
        use: b.use || 'Commercial / Residential',
      };

      const edges = new THREE.EdgesGeometry(geom, 20);
      const lineMat = new THREE.LineBasicMaterial({ color: new THREE.Color(edgeColor), linewidth: 1.2 });
      group.add(new THREE.LineSegments(edges, lineMat));

      contextGroup.add(group);
      interactiveObjects.push(baseMesh);
    }
  }

  // Vehicular Road Network
  if (DATA.roads && Array.isArray(DATA.roads)) {
    for (const r of DATA.roads) {
      if (!r.vertices || !r.faces) continue;
      const { group } = createArchitecturalVolume(r.vertices, r.faces, 0xffffff, 1.0, true);
      contextGroup.add(group);
    }
    if (DATA.roadOutlines && Array.isArray(DATA.roadOutlines)) {
      for (const outline of DATA.roadOutlines) {
        if (outline.length >= 2) {
          const rPts = outline.map(p => new THREE.Vector3(p[0], 0.04, -p[1]));
          const rGeom = new THREE.BufferGeometry().setFromPoints(rPts);
          const rMat = new THREE.LineBasicMaterial({ color: 0xd1d5db, linewidth: 1.0 });
          contextGroup.add(new THREE.Line(rGeom, rMat));
        }
      }
    }
  }

  // Green Spaces / Parks
  if (DATA.greenSpaces && Array.isArray(DATA.greenSpaces)) {
    for (const g of DATA.greenSpaces) {
      if (!g.vertices || !g.faces) continue;
      const { group } = createArchitecturalVolume(g.vertices, g.faces, 0xdcfce7, 1.0, true);
      contextGroup.add(group);
    }
  }

  scene.add(contextGroup);

  // Testing Site Parcel
  const siteGroup = new THREE.Group();
  siteGroup.name = "testingSiteParcel";
  scene.add(siteGroup);

  const siteFaceColor = 0xfca5a5; // Soft Coral Red

  function renderSiteParcel(customPolygon) {
    while (siteGroup.children.length > 0) {
      const child = siteGroup.children.pop();
      if (child.geometry) child.geometry.dispose();
    }

    // Remove from interactiveObjects
    for (let i = interactiveObjects.length - 1; i >= 0; i--) {
      if (interactiveObjects[i].userData && interactiveObjects[i].userData.isSite) {
        interactiveObjects.splice(i, 1);
      }
    }

    if (customPolygon && Array.isArray(customPolygon) && customPolygon.length >= 3) {
      const shape = new THREE.Shape();
      customPolygon.forEach((p, idx) => {
        const px = Number(p.x ?? p[0] ?? 0);
        const py = Number(p.y ?? p[1] ?? 0);
        if (idx === 0) shape.moveTo(px, py);
        else shape.lineTo(px, py);
      });

      const geom = new THREE.ExtrudeGeometry(shape, { depth: 0.20, bevelEnabled: false });
      geom.rotateX(-Math.PI / 2);

      const baseMat = new THREE.MeshLambertMaterial({
        color: new THREE.Color(siteFaceColor),
        emissive: new THREE.Color(siteFaceColor).multiplyScalar(0.55),
        transparent: true,
        opacity: 0.92,
      });
      const baseMesh = new THREE.Mesh(geom, baseMat);
      baseMesh.receiveShadow = true;
      baseMesh.userData = { isSite: true, area: DATA.siteArea || 0 };
      siteGroup.add(baseMesh);
      interactiveObjects.push(baseMesh);

      const outPts = customPolygon.map((p) => new THREE.Vector3(Number(p.x ?? p[0] ?? 0), 0.26, -Number(p.y ?? p[1] ?? 0)));
      outPts.push(outPts[0].clone());
      const siteLineGeom = new THREE.BufferGeometry().setFromPoints(outPts);
      const siteLineMat = new THREE.LineBasicMaterial({ color: 0xef4444, linewidth: 2.5 });
      siteGroup.add(new THREE.Line(siteLineGeom, siteLineMat));
    } else if (DATA.site && DATA.site.vertices && DATA.site.faces) {
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

      if (DATA.sitePerimeter && DATA.sitePerimeter.length >= 3) {
        const outPts = DATA.sitePerimeter.map((p) => new THREE.Vector3(p[0], 0.26, -p[1]));
        outPts.push(outPts[0].clone());
        const siteLineGeom = new THREE.BufferGeometry().setFromPoints(outPts);
        const siteLineMat = new THREE.LineBasicMaterial({ color: 0xef4444, linewidth: 2.5 });
        siteGroup.add(new THREE.Line(siteLineGeom, siteLineMat));
      }
    }
  }

  renderSiteParcel(null);

  // Handle Optimizer Placements and UI Messages
  window.addEventListener('message', (event) => {
    if (!event.data) return;

    if (event.data.type === 'set_context_visibility') {
      const isVisible = event.data.visible !== false;
      contextGroup.visible = isVisible;
      if (!isVisible && event.data.customPolygon) {
        renderSiteParcel(event.data.customPolygon);
      } else if (isVisible) {
        renderSiteParcel(null);
      }
      return;
    }

    if (event.data.type === 'set_camera_mode' && event.data.mode) {
      setCamera(event.data.mode === 'axonometric' ? 'ortho' : 'persp');
      return;
    }

    if (event.data.type !== 'optimizer_placements') return;
    const { placements, boundaries, isReal } = event.data;
    if (isReal === false && Array.isArray(boundaries) && boundaries.length > 0 && boundaries[0].polygon) {
      renderSiteParcel(boundaries[0].polygon);
    } else if (isReal === true) {
      renderSiteParcel(null);
    }
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

          const dot = faceNormal.dot(sunVector);
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
      hoveredObj.material.color.setHex(hoveredObj.userData.isSite ? 0xfca5a5 : 0xffffff);
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

  try {
    window.parent.postMessage({ type: 'viewer_ready' }, '*');
  } catch (e) {}
}
