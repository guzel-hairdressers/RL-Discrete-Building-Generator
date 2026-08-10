// Modular Three.js Engine for 3D Urban Context Rendering
(function() {
  let scene, camera, renderer, controls;
  let isAxonometric = true;
  let currentSiteData = null;
  let buildingGroup, roadGroup, gridGroup, shadowPlane;
  let raycaster, mouse, tooltipEl;
  let gizmoRenderer, gizmoScene, gizmoCamera;

  function init() {
    const container = document.getElementById('canvas-container');
    const width = container.clientWidth;
    const height = container.clientHeight;

    // Scene setup
    scene = new THREE.Scene();
    scene.background = new THREE.Color(0xf8fafc);

    // Cameras
    const aspect = width / height;
    const d = 160;
    
    // Axonometric (Orthographic) Camera
    const orthoCam = new THREE.OrthographicCamera(-d * aspect, d * aspect, d, -d, 1, 2000);
    orthoCam.position.set(220, 220, 220);
    orthoCam.lookAt(0, 0, 0);

    // Perspective Camera
    const perspCam = new THREE.PerspectiveCamera(45, aspect, 1, 2000);
    perspCam.position.set(220, 180, 220);
    perspCam.lookAt(0, 0, 0);

    camera = orthoCam;

    // WebGL Renderer with Shadows
    renderer = new THREE.WebGLRenderer({ antialias: true, powerPreference: 'high-performance' });
    renderer.setSize(width, height);
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.shadowMap.enabled = true;
    renderer.shadowMap.type = THREE.PCFSoftShadowMap;
    container.appendChild(renderer.domElement);

    // Orbit Controls
    controls = new THREE.OrbitControls(camera, renderer.domElement);
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
    buildingGroup = new THREE.Group();
    roadGroup = new THREE.Group();
    gridGroup = new THREE.Group();
    scene.add(buildingGroup);
    scene.add(roadGroup);
    scene.add(gridGroup);

    // 200m x 200m Ground Shadow Plane (-100m to +100m)
    const planeGeo = new THREE.PlaneGeometry(200, 200);
    const planeMat = new THREE.ShadowMaterial({ opacity: 0.12 });
    shadowPlane = new THREE.Mesh(planeGeo, planeMat);
    shadowPlane.rotation.x = -Math.PI / 2;
    shadowPlane.receiveShadow = true;
    scene.add(shadowPlane);

    // Build Ground Grid Tick Markers (-100m to +100m)
    createGroundGrid();

    // Raycasting for Pure White Hover Tooltips
    raycaster = new THREE.Raycaster();
    mouse = new THREE.Vector2();
    tooltipEl = document.getElementById('tooltip');

    window.addEventListener('mousemove', onMouseMove);
    window.addEventListener('resize', onWindowResize);

    // Setup Camera Toggle Buttons
    document.getElementById('btn-axono').addEventListener('click', () => switchCamera(true));
    document.getElementById('btn-persp').addEventListener('click', () => switchCamera(false));

    // Gizmo setup
    setupGizmo();

    // Animation loop
    animate();
  }

  function createGroundGrid() {
    const gridHelper = new THREE.GridHelper(200, 4, 0xd1d5db, 0xe2e8f0);
    gridGroup.add(gridHelper);
  }

  function switchCamera(axono) {
    if (isAxonometric === axono) return;
    isAxonometric = axono;

    document.getElementById('btn-axono').classList.toggle('active', axono);
    document.getElementById('btn-persp').classList.toggle('active', !axono);

    const aspect = window.innerWidth / window.innerHeight;
    const pos = camera.position.clone();
    const target = controls.target.clone();

    if (axono) {
      const d = 160;
      camera = new THREE.OrthographicCamera(-d * aspect, d * aspect, d, -d, 1, 2000);
    } else {
      camera = new THREE.PerspectiveCamera(45, aspect, 1, 2000);
    }

    camera.position.copy(pos);
    camera.lookAt(target);
    controls.object = camera;
    controls.update();
  }

  function loadSiteContext(site) {
    currentSiteData = site;
    
    // Clear previous geometries
    while (buildingGroup.children.length > 0) {
      const child = buildingGroup.children.pop();
      if (child.geometry) child.geometry.dispose();
    }

    // Generate Procedural Architectural Massings matching exact site area & tier
    const bldgCount = site.building_count || 30;
    const avgH = site.avg_height_m || 25;
    const maxH = site.max_height_m || 65;

    // Center site parcel polygon (Coral Red Highlight)
    const siteArea = site.site_area_m2 || 800;
    const siteSide = Math.sqrt(siteArea);
    const siteGeo = new THREE.BoxGeometry(siteSide, 0.2, siteSide);
    const siteMat = new THREE.MeshStandardMaterial({
      color: 0xf87171, // Soft Coral Red
      roughness: 0.4,
      metalness: 0.1
    });
    const siteMesh = new THREE.Mesh(siteGeo, siteMat);
    siteMesh.position.set(0, 0.1, 0);
    siteMesh.receiveShadow = true;
    siteMesh.userData = {
      isSiteParcel: true,
      area: siteArea,
      tier: site.area_tier,
      far: site.far || 2.5,
      city: site.city_name || 'City Center'
    };
    buildingGroup.add(siteMesh);

    // Surrounding Context Buildings (Unlit Monochrome White Volumes)
    const seed = site.site_id.split('').reduce((acc, c) => acc + c.charCodeAt(0), 0);
    let rng = seed;
    function pseudorandom() {
      rng = (rng * 9301 + 49297) % 233280;
      return rng / 233280;
    }

    const matWhite = new THREE.MeshStandardMaterial({
      color: 0xffffff,
      roughness: 0.8,
      metalness: 0.05
    });

    const edgeMat = new THREE.LineBasicMaterial({ color: 0x94a3b8, linewidth: 1 });

    for (let i = 0; i < bldgCount; i++) {
      const angle = pseudorandom() * Math.PI * 2;
      const radius = 18 + pseudorandom() * 75; // strictly within 100m radius
      const x = Math.cos(angle) * radius;
      const z = Math.sin(angle) * radius;

      // Skip overlap with center parcel
      if (Math.abs(x) < siteSide / 1.5 && Math.abs(z) < siteSide / 1.5) continue;

      const bw = 12 + pseudorandom() * 24;
      const bd = 12 + pseudorandom() * 24;
      const h = 8 + pseudorandom() * (maxH - 8);

      const bGeo = new THREE.BoxGeometry(bw, h, bd);
      const bMesh = new THREE.Mesh(bGeo, matWhite);
      bMesh.position.set(x, h / 2, z);
      bMesh.castShadow = true;
      bMesh.receiveShadow = true;

      // Edge wireframe segments
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
        footprint: footprint,
        storeys: storeys,
        use: use
      };

      buildingGroup.add(bMesh);
    }
  }

  function onMouseMove(event) {
    mouse.x = (event.clientX / window.innerWidth) * 2 - 1;
    mouse.y = -(event.clientY / window.innerHeight) * 2 + 1;

    raycaster.setFromCamera(mouse, camera);
    const intersects = raycaster.intersectObjects(buildingGroup.children);

    if (intersects.length > 0) {
      const hit = intersects[0].object;
      const data = hit.userData;

      if (data.isSiteParcel) {
        tooltipEl.style.display = 'block';
        tooltipEl.style.left = `${event.clientX + 15}px`;
        tooltipEl.style.top = `${event.clientY + 15}px`;
        tooltipEl.innerHTML = `
          <strong>Primary Site Parcel</strong><br>
          Site Area: ${data.area.toFixed(1)} m² (${data.tier} Tier)<br>
          Target FAR: ${data.far.toFixed(2)}<br>
          Location: ${data.city}
        `;
      } else if (data.isBuilding) {
        tooltipEl.style.display = 'block';
        tooltipEl.style.left = `${event.clientX + 15}px`;
        tooltipEl.style.top = `${event.clientY + 15}px`;
        tooltipEl.innerHTML = `
          <strong>${data.use}</strong><br>
          Footprint: ${data.footprint} m²<br>
          Height: ${data.height} m<br>
          Storeys: ${data.storeys}
        `;
      } else {
        tooltipEl.style.display = 'none';
      }
    } else {
      tooltipEl.style.display = 'none';
    }
  }

  function setupGizmo() {
    const container = document.getElementById('gizmo-container');
    if (!container) return;

    gizmoScene = new THREE.Scene();
    gizmoCamera = new THREE.OrthographicCamera(-1.2, 1.2, 1.2, -1.2, 0.1, 10);
    gizmoCamera.position.set(0, 0, 5);

    gizmoRenderer = new THREE.WebGLRenderer({ alpha: true, antialias: true });
    gizmoRenderer.setSize(100, 100);
    container.appendChild(gizmoRenderer.domElement);

    // Axes
    const axesHelper = new THREE.AxesHelper(0.8);
    gizmoScene.add(axesHelper);
  }

  function onWindowResize() {
    const width = window.innerWidth;
    const height = window.innerHeight;
    const aspect = width / height;

    if (camera.isOrthographicCamera) {
      const d = 160;
      camera.left = -d * aspect;
      camera.right = d * aspect;
      camera.top = d;
      camera.bottom = -d;
    } else {
      camera.aspect = aspect;
    }
    camera.updateProjectionMatrix();
    renderer.setSize(width, height);
  }

  function animate() {
    requestAnimationFrame(animate);
    controls.update();

    if (gizmoCamera && gizmoRenderer) {
      gizmoCamera.quaternion.copy(camera.quaternion).invert();
      gizmoRenderer.render(gizmoScene, gizmoCamera);
    }

    renderer.render(scene, camera);
  }

  // Export engine API
  window.ThreeEngine = {
    init,
    loadSiteContext,
    switchCamera
  };

  document.addEventListener('DOMContentLoaded', init);
})();
