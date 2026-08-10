import React, { useEffect, useRef } from 'react';
import * as THREE from 'three';
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js';
import { useStore } from '../store/useStore';

export const ThreeCanvas = () => {
  const mountRef = useRef(null);
  const gizmoRef = useRef(null);
  const tooltipRef = useRef(null);

  const filteredSites = useStore((s) => s.filteredSites);
  const activeSiteIndex = useStore((s) => s.activeSiteIndex);
  const viewMode = useStore((s) => s.viewMode);

  const activeSite = filteredSites[activeSiteIndex];

  // Store Three.js instances in ref
  const engineRef = useRef({
    scene: null,
    camera: null,
    orthoCam: null,
    perspCam: null,
    renderer: null,
    controls: null,
    buildingGroup: null,
    gizmoScene: null,
    gizmoCamera: null,
    gizmoRenderer: null,
  });

  // Initialize Three.js WebGL Renderer
  useEffect(() => {
    const container = mountRef.current;
    if (!container) return;

    const width = container.clientWidth;
    const height = container.clientHeight;
    const aspect = width / height;

    // Scene
    const scene = new THREE.Scene();
    scene.background = new THREE.Color(0xf8fafc);

    // Cameras
    const d = 160;
    const orthoCam = new THREE.OrthographicCamera(-d * aspect, d * aspect, d, -d, 1, 2000);
    orthoCam.position.set(220, 220, 220);
    orthoCam.lookAt(0, 0, 0);

    const perspCam = new THREE.PerspectiveCamera(45, aspect, 1, 2000);
    perspCam.position.set(220, 180, 220);
    perspCam.lookAt(0, 0, 0);

    const camera = orthoCam;

    // Renderer withPCFSoftShadowMap
    const renderer = new THREE.WebGLRenderer({ antialias: true, powerPreference: 'high-performance' });
    renderer.setSize(width, height);
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.shadowMap.enabled = true;
    renderer.shadowMap.type = THREE.PCFSoftShadowMap;
    container.appendChild(renderer.domElement);

    // Orbit Controls
    const controls = new OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;
    controls.dampingFactor = 0.05;
    controls.maxPolarAngle = Math.PI / 2 - 0.01;

    // Lighting
    const ambientLight = new THREE.AmbientLight(0xffffff, 0.7);
    scene.add(ambientLight);

    const dirLight = new THREE.DirectionalLight(0xffffff, 0.65);
    dirLight.position.set(150, 250, 100);
    dirLight.castShadow = true;
    dirLight.shadow.mapSize.width = 2048;
    dirLight.shadow.mapSize.height = 2048;
    dirLight.shadow.camera.near = 10;
    dirLight.shadow.camera.far = 600;
    dirLight.shadow.camera.left = -160;
    dirLight.shadow.camera.right = 160;
    dirLight.shadow.camera.top = 160;
    dirLight.shadow.camera.bottom = -160;
    dirLight.shadow.bias = -0.0005;
    scene.add(dirLight);

    // Groups
    const buildingGroup = new THREE.Group();
    scene.add(buildingGroup);

    // 200m x 200m Ground Shadow Plane (-100m to +100m)
    const planeGeo = new THREE.PlaneGeometry(200, 200);
    const planeMat = new THREE.ShadowMaterial({ opacity: 0.12 });
    const shadowPlane = new THREE.Mesh(planeGeo, planeMat);
    shadowPlane.rotation.x = -Math.PI / 2;
    shadowPlane.receiveShadow = true;
    scene.add(shadowPlane);

    // Ground Grid Helper
    const gridHelper = new THREE.GridHelper(200, 4, 0xd1d5db, 0xe2e8f0);
    scene.add(gridHelper);

    // Gizmo Renderer Setup
    const gizmoContainer = gizmoRef.current;
    let gizmoScene = null, gizmoCamera = null, gizmoRenderer = null;
    if (gizmoContainer) {
      gizmoScene = new THREE.Scene();
      gizmoCamera = new THREE.OrthographicCamera(-1.2, 1.2, 1.2, -1.2, 0.1, 10);
      gizmoCamera.position.set(0, 0, 5);

      gizmoRenderer = new THREE.WebGLRenderer({ alpha: true, antialias: true });
      gizmoRenderer.setSize(100, 100);
      gizmoContainer.appendChild(gizmoRenderer.domElement);

      const axesHelper = new THREE.AxesHelper(0.8);
      gizmoScene.add(axesHelper);
    }

    // Raycaster for Hover Tooltips
    const raycaster = new THREE.Raycaster();
    const mouse = new THREE.Vector2();

    const handleMouseMove = (event) => {
      if (!tooltipRef.current) return;
      mouse.x = (event.clientX / window.innerWidth) * 2 - 1;
      mouse.y = -(event.clientY / window.innerHeight) * 2 + 1;

      raycaster.setFromCamera(mouse, engineRef.current.camera);
      const intersects = raycaster.intersectObjects(buildingGroup.children);

      if (intersects.length > 0) {
        const hit = intersects[0].object;
        const data = hit.userData;

        if (data.isSiteParcel) {
          tooltipRef.current.style.display = 'block';
          tooltipRef.current.style.left = `${event.clientX + 15}px`;
          tooltipRef.current.style.top = `${event.clientY + 15}px`;
          tooltipRef.current.innerHTML = `
            <strong>Primary Site Parcel</strong><br>
            Site Area: ${data.area.toFixed(1)} m² (${data.tier} Tier)<br>
            Target FAR: ${data.far.toFixed(2)}<br>
            Location: ${data.city}
          `;
        } else if (data.isBuilding) {
          tooltipRef.current.style.display = 'block';
          tooltipRef.current.style.left = `${event.clientX + 15}px`;
          tooltipRef.current.style.top = `${event.clientY + 15}px`;
          tooltipRef.current.innerHTML = `
            <strong>${data.use}</strong><br>
            Footprint: ${data.footprint} m²<br>
            Height: ${data.height} m<br>
            Storeys: ${data.storeys}
          `;
        }
      } else {
        tooltipRef.current.style.display = 'none';
      }
    };

    window.addEventListener('mousemove', handleMouseMove);

    // Resize Handler
    const handleResize = () => {
      const w = container.clientWidth;
      const h = container.clientHeight;
      const asp = w / h;

      if (engineRef.current.camera.isOrthographicCamera) {
        const d = 160;
        engineRef.current.camera.left = -d * asp;
        engineRef.current.camera.right = d * asp;
        engineRef.current.camera.top = d;
        engineRef.current.camera.bottom = -d;
      } else {
        engineRef.current.camera.aspect = asp;
      }
      engineRef.current.camera.updateProjectionMatrix();
      renderer.setSize(w, h);
    };

    window.addEventListener('resize', handleResize);

    // Animation Loop
    let animId;
    const animate = () => {
      animId = requestAnimationFrame(animate);
      controls.update();

      if (gizmoCamera && gizmoRenderer && engineRef.current.camera) {
        gizmoCamera.quaternion.copy(engineRef.current.camera.quaternion).invert();
        gizmoRenderer.render(gizmoScene, gizmoCamera);
      }

      renderer.render(scene, engineRef.current.camera);
    };

    animate();

    // Store references
    engineRef.current = {
      scene,
      camera,
      orthoCam,
      perspCam,
      renderer,
      controls,
      buildingGroup,
      gizmoScene,
      gizmoCamera,
      gizmoRenderer,
    };

    return () => {
      cancelAnimationFrame(animId);
      window.removeEventListener('mousemove', handleMouseMove);
      window.removeEventListener('resize', handleResize);
      renderer.dispose();
      if (container.contains(renderer.domElement)) {
        container.removeChild(renderer.domElement);
      }
    };
  }, []);

  // Update Camera View Mode (Axonometric vs Perspective)
  useEffect(() => {
    const { orthoCam, perspCam, controls } = engineRef.current;
    if (!orthoCam || !perspCam || !controls) return;

    const targetCam = viewMode === 'axonometric' ? orthoCam : perspCam;
    const pos = engineRef.current.camera.position.clone();
    const target = controls.target.clone();

    targetCam.position.copy(pos);
    targetCam.lookAt(target);
    controls.object = targetCam;
    controls.update();
    engineRef.current.camera = targetCam;
  }, [viewMode]);

  // Update 3D Geometry when activeSite changes (<5ms)
  useEffect(() => {
    const { buildingGroup } = engineRef.current;
    if (!buildingGroup || !activeSite) return;

    // Clear previous objects
    while (buildingGroup.children.length > 0) {
      const child = buildingGroup.children.pop();
      if (child.geometry) child.geometry.dispose();
    }

    // Coral Red Highlighted Center Site Parcel
    const siteArea = activeSite.site_area_m2 || 800;
    const siteSide = Math.sqrt(siteArea);
    const siteGeo = new THREE.BoxGeometry(siteSide, 0.2, siteSide);
    const siteMat = new THREE.MeshStandardMaterial({
      color: 0xf87171, // Soft Coral Red
      roughness: 0.4,
      metalness: 0.1,
    });
    const siteMesh = new THREE.Mesh(siteGeo, siteMat);
    siteMesh.position.set(0, 0.1, 0);
    siteMesh.receiveShadow = true;
    siteMesh.userData = {
      isSiteParcel: true,
      area: siteArea,
      tier: activeSite.area_tier,
      far: activeSite.far || 2.5,
      city: activeSite.city_name || activeSite.city_code.toUpperCase(),
    };
    buildingGroup.add(siteMesh);

    // Context Buildings (Unlit Monochrome Paper White)
    const bldgCount = activeSite.building_count || 32;
    const maxH = activeSite.max_height_m || 65;

    const seed = activeSite.site_id.split('').reduce((acc, c) => acc + c.charCodeAt(0), 0);
    let rng = seed;
    function pseudorandom() {
      rng = (rng * 9301 + 49297) % 233280;
      return rng / 233280;
    }

    const matWhite = new THREE.MeshStandardMaterial({
      color: 0xffffff,
      roughness: 0.8,
      metalness: 0.05,
    });

    const edgeMat = new THREE.LineBasicMaterial({ color: 0x94a3b8 });

    for (let i = 0; i < bldgCount; i++) {
      const angle = pseudorandom() * Math.PI * 2;
      const radius = 18 + pseudorandom() * 75; // 100m radius cutoff
      const x = Math.cos(angle) * radius;
      const z = Math.sin(angle) * radius;

      if (Math.abs(x) < siteSide / 1.5 && Math.abs(z) < siteSide / 1.5) continue;

      const bw = 12 + pseudorandom() * 24;
      const bd = 12 + pseudorandom() * 24;
      const h = 8 + pseudorandom() * (maxH - 8);

      const bGeo = new THREE.BoxGeometry(bw, h, bd);
      const bMesh = new THREE.Mesh(bGeo, matWhite);
      bMesh.position.set(x, h / 2, z);
      bMesh.castShadow = true;
      bMesh.receiveShadow = true;

      const edges = new THREE.EdgesGeometry(bGeo);
      const line = new THREE.LineSegments(edges, edgeMat);
      bMesh.add(line);

      const footprint = Math.round(bw * bd);
      const storeys = Math.round(h / 3.2);
      const useTypes = ['Residential / Mixed-Use', 'Commercial / Office', 'Retail / Residential', 'Civic / Cultural'];
      const use = useTypes[Math.floor(pseudorandom() * useTypes.length)];

      bMesh.userData = {
        isBuilding: true,
        height: h.toFixed(1),
        footprint,
        storeys,
        use,
      };

      buildingGroup.add(bMesh);
    }
  }, [activeSite]);

  return (
    <>
      <div id="canvas-container" ref={mountRef} />
      <div id="gizmo-container" ref={gizmoRef} />
      <div id="tooltip" ref={tooltipRef} />
    </>
  );
};
