import React, { useState, useEffect, useRef } from 'react';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';
import { useStore } from '../store/useStore';
import './CustomSiteModal.css';

// Fix Leaflet marker icon path in bundled Vite app
try {
  if (L && L.Icon && L.Icon.Default && L.Icon.Default.prototype) {
    delete L.Icon.Default.prototype._getIconUrl;
    L.Icon.Default.mergeOptions({
      iconRetinaUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.7.1/images/marker-icon-2x.png',
      iconUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.7.1/images/marker-icon.png',
      shadowUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.7.1/images/marker-shadow.png',
    });
  }
} catch (e) {
  console.warn('Leaflet icon config warning:', e);
}

export const CustomSiteModal = () => {
  const customModalOpen = useStore((s) => s.customModalOpen);
  const setCustomModalOpen = useStore((s) => s.setCustomModalOpen);
  const addCustomSite = useStore((s) => s.addCustomSite);

  const mapRef = useRef(null);
  const mapInstanceRef = useRef(null);
  const markerRef = useRef(null);
  const drawLayerRef = useRef(null);
  const drawGroupRef = useRef(null);
  const abortControllerRef = useRef(null);
  const stepTimersRef = useRef([]);

  const [selectMode, setSelectMode] = useState('marker'); // 'marker' | 'draw'
  const [drawnPoints, setDrawnPoints] = useState([]); // Array of [lat, lng]
  const [selectedIndex, setSelectedIndex] = useState(null); // Index of selected vertex
  const [mapReady, setMapReady] = useState(0); // Map initialization signal
  const [roadSetback, setRoadSetback] = useState(2.0);
  const [buildingSetback, setBuildingSetback] = useState(3.0);
  const [parcelType, setParcelType] = useState('convex_hull'); // 'convex_hull' | 'voronoi'
  const selectModeRef = useRef(selectMode);
  selectModeRef.current = selectMode;
  const drawnPointsRef = useRef(drawnPoints);
  drawnPointsRef.current = drawnPoints;
  const selectedIndexRef = useRef(selectedIndex);
  selectedIndexRef.current = selectedIndex;

  const [searchQuery, setSearchQuery] = useState('');
  const [selectedLat, setSelectedLat] = useState(48.8566);
  const [selectedLon, setSelectedLon] = useState(2.3522);
  const [locationName, setLocationName] = useState('Paris');
  const [isFetching, setIsFetching] = useState(false);
  const [statusMsg, setStatusMsg] = useState('');

  const updateCoords = async (lat, lng) => {
    setSelectedLat(lat);
    setSelectedLon(lng);
    try {
      const res = await fetch(`https://nominatim.openstreetmap.org/reverse?format=json&accept-language=en&lat=${lat}&lon=${lng}`);
      const data = await res.json();
      if (data && data.address) {
        const a = data.address;
        const place = a.city || a.town || a.village || a.suburb || a.municipality || a.county || a.state || 'Custom Location';
        setLocationName(place);
      }
    } catch (e) {}
  };

  // Initialize Leaflet Map when modal opens
  useEffect(() => {
    if (!customModalOpen) return;

    let timer = setTimeout(() => {
      if (!mapRef.current) return;

      try {
        if (mapInstanceRef.current) {
          mapInstanceRef.current.invalidateSize();
          setMapReady((n) => n + 1);
          return;
        }

        if (mapRef.current._leaflet_id) {
          mapRef.current._leaflet_id = null;
        }

        const map = L.map(mapRef.current).setView([selectedLat, selectedLon], 15);

        L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
          attribution: '&copy; OpenStreetMap',
          maxZoom: 19,
        }).addTo(map);

        const marker = L.marker([selectedLat, selectedLon], { draggable: true }).addTo(map);
        markerRef.current = marker;

        marker.on('dragend', (e) => {
          const { lat, lng } = e.target.getLatLng();
          updateCoords(lat, lng);
        });

        map.on('click', (e) => {
          const { lat, lng } = e.latlng;
          if (selectModeRef.current === 'draw') {
            if (selectedIndexRef.current !== null) {
              setSelectedIndex(null);
            } else {
              const nextPts = [...drawnPointsRef.current, [lat, lng]];
              setDrawnPoints(nextPts);
              setSelectedIndex(null); // DO NOT select newly placed point automatically!
              if (nextPts.length >= 1) {
                const avgLat = nextPts.reduce((acc, p) => acc + p[0], 0) / nextPts.length;
                const avgLng = nextPts.reduce((acc, p) => acc + p[1], 0) / nextPts.length;
                updateCoords(avgLat, avgLng);
              }
            }
          } else {
            marker.setLatLng([lat, lng]);
            updateCoords(lat, lng);
          }
        });

        mapInstanceRef.current = map;
        setMapReady((n) => n + 1);
      } catch (err) {
        console.error('Leaflet map init error:', err);
      }
    }, 100);

    return () => {
      clearTimeout(timer);
      if (mapInstanceRef.current) {
        try {
          mapInstanceRef.current.remove();
        } catch (e) {}
        mapInstanceRef.current = null;
      }
    };
  }, [customModalOpen]);

  const calcPolygonAreaM2 = (pts) => {
    if (!pts || pts.length < 3) return 0;
    const refLat = pts[0][0];
    const refLon = pts[0][1];
    const rEarth = 6371000.0;
    const meterPts = pts.map(([lat, lon]) => {
      const dLat = (lat - refLat) * Math.PI / 180;
      const dLon = (lon - refLon) * Math.PI / 180;
      return [
        dLon * rEarth * Math.cos(refLat * Math.PI / 180),
        dLat * rEarth
      ];
    });
    let area = 0;
    for (let i = 0; i < meterPts.length; i++) {
      const j = (i + 1) % meterPts.length;
      area += meterPts[i][0] * meterPts[j][1];
      area -= meterPts[j][0] * meterPts[i][1];
    }
    return Math.round(Math.abs(area) / 2.0);
  };

  const findClosestSegmentIndex = (pts, clickLat, clickLng) => {
    if (pts.length < 2) return 0;
    let minSqDist = Infinity;
    let bestIdx = 0;
    for (let i = 0; i < pts.length; i++) {
      const p1 = pts[i];
      const p2 = pts[(i + 1) % pts.length];
      const dx = p2[1] - p1[1];
      const dy = p2[0] - p1[0];
      const lenSq = dx * dx + dy * dy;
      let t = lenSq === 0 ? 0 : ((clickLng - p1[1]) * dx + (clickLat - p1[0]) * dy) / lenSq;
      t = Math.max(0, Math.min(1, t));
      const projLat = p1[0] + t * dy;
      const projLng = p1[1] + t * dx;
      const sqDist = (clickLat - projLat) ** 2 + (clickLng - projLng) ** 2;
      if (sqDist < minSqDist) {
        minSqDist = sqDist;
        bestIdx = i;
      }
    }
    return bestIdx;
  };

  // Render polygon/polyline layer on Leaflet map dynamically
  useEffect(() => {
    const map = mapInstanceRef.current;
    if (!map) return;

    if (selectMode === 'marker') {
      if (markerRef.current && !map.hasLayer(markerRef.current)) {
        markerRef.current.addTo(map);
      }
      if (drawLayerRef.current) {
        map.removeLayer(drawLayerRef.current);
        drawLayerRef.current = null;
      }
      if (drawGroupRef.current) {
        map.removeLayer(drawGroupRef.current);
        drawGroupRef.current = null;
      }
      return;
    }

    if (markerRef.current && map.hasLayer(markerRef.current)) {
      map.removeLayer(markerRef.current);
    }

    if (drawLayerRef.current) {
      map.removeLayer(drawLayerRef.current);
      drawLayerRef.current = null;
    }
    if (drawGroupRef.current) {
      map.removeLayer(drawGroupRef.current);
      drawGroupRef.current = null;
    }

    if (drawnPoints.length === 0) return;

    const layerGroup = L.layerGroup().addTo(map);
    drawLayerRef.current = layerGroup;

    let hitLine = null;

    if (drawnPoints.length >= 3) {
      // Shaded polygon interior (non-interactive so clicks pass through to map background)
      const filledPoly = L.polygon(drawnPoints, {
        color: '#dc2626',
        weight: 3,
        fillColor: '#ef4444',
        fillOpacity: 0.35,
        interactive: false,
      });
      layerGroup.addLayer(filledPoly);

      // Boundary line hit-target for point insertion (interactive finger pointer only near edge line)
      hitLine = L.polyline([...drawnPoints, drawnPoints[0]], {
        color: '#dc2626',
        weight: 14,
        opacity: 0.0001,
        interactive: true,
      });
      layerGroup.addLayer(hitLine);
    } else {
      const visibleLine = L.polyline(drawnPoints, {
        color: '#dc2626',
        weight: 3,
        interactive: false,
      });
      layerGroup.addLayer(visibleLine);

      hitLine = L.polyline(drawnPoints, {
        color: '#dc2626',
        weight: 14,
        opacity: 0.0001,
        interactive: true,
      });
      layerGroup.addLayer(hitLine);
    }

    // Split line segment on click on boundary edge line
    if (hitLine) {
      hitLine.on('click', (e) => {
        L.DomEvent.stopPropagation(e);
        const { lat, lng } = e.latlng;
        const pts = drawnPointsRef.current;
        if (pts.length >= 2) {
          const insertIdx = findClosestSegmentIndex(pts, lat, lng);
          const nextPts = [...pts.slice(0, insertIdx + 1), [lat, lng], ...pts.slice(insertIdx + 1)];
          setDrawnPoints(nextPts);
          setSelectedIndex(insertIdx + 1);
        }
      });
    }

    const normalIcon = L.divIcon({
      className: 'vertex-handle-icon',
      html: '<div style="width: 9px; height: 9px; background: #ffffff; border: 2px solid #dc2626; border-radius: 50%; cursor: pointer;"></div>',
      iconSize: [9, 9],
      iconAnchor: [4.5, 4.5],
    });

    const selectedIcon = L.divIcon({
      className: 'vertex-handle-icon-selected',
      html: '<div style="width: 10px; height: 10px; background: #dc2626; border: 2px solid #ffffff; border-radius: 50%; cursor: grab; box-shadow: 0 1px 3px rgba(0,0,0,0.3);"></div>',
      iconSize: [10, 10],
      iconAnchor: [5, 5],
    });

    const group = L.layerGroup();
    drawnPoints.forEach((pt, idx) => {
      const isSelected = selectedIndex === idx;
      const handleMarker = L.marker(pt, {
        icon: isSelected ? selectedIcon : normalIcon,
        draggable: isSelected, // ONLY SELECTED VERTEX IS DRAGGABLE!
      });

      handleMarker.on('click', (e) => {
        L.DomEvent.stopPropagation(e);
        setSelectedIndex(idx);
      });

      handleMarker.on('drag', (e) => {
        const { lat, lng } = e.target.getLatLng();
        if (drawLayerRef.current) {
          const tempPts = [...drawnPointsRef.current];
          tempPts[idx] = [lat, lng];
          drawLayerRef.current.eachLayer((layer) => {
            if (typeof layer.setLatLngs === 'function') {
              if (layer instanceof L.Polygon) {
                layer.setLatLngs(tempPts);
              } else if (layer instanceof L.Polyline) {
                layer.setLatLngs(tempPts.length >= 3 ? [...tempPts, tempPts[0]] : tempPts);
              }
            }
          });
        }
      });

      handleMarker.on('dragend', (e) => {
        const { lat, lng } = e.target.getLatLng();
        setDrawnPoints((prev) => {
          const updated = [...prev];
          updated[idx] = [lat, lng];
          return updated;
        });
      });

      group.addLayer(handleMarker);
    });
    group.addTo(map);
    drawGroupRef.current = group;
  }, [drawnPoints, selectedIndex, selectMode, customModalOpen, mapReady]);

  if (!customModalOpen) return null;

  const drawnArea = calcPolygonAreaM2(drawnPoints);

  // Search address / city using OpenStreetMap Nominatim
  const handleSearch = async (e) => {
    e?.preventDefault();
    if (!searchQuery.trim()) return;

    setStatusMsg('Searching location...');
    try {
      const res = await fetch(
        `https://nominatim.openstreetmap.org/search?format=json&accept-language=en&q=${encodeURIComponent(searchQuery)}`
      );
      const data = await res.json();
      if (Array.isArray(data) && data.length > 0) {
        const first = data[0];
        const lat = parseFloat(first.lat);
        const lon = parseFloat(first.lon);
        const name = first.display_name.split(',')[0].trim();

        setSelectedLat(lat);
        setSelectedLon(lon);
        setLocationName(name);

        if (mapInstanceRef.current) {
          mapInstanceRef.current.setView([lat, lon], 16);
          if (markerRef.current) markerRef.current.setLatLng([lat, lon]);
        }
        setStatusMsg('');
      } else {
        setStatusMsg('Location not found. Try another search.');
      }
    } catch (err) {
      if (err.name !== 'AbortError') {
        setStatusMsg('Geocoding error.');
      }
    }
  };

  const clearStepTimers = () => {
    stepTimersRef.current.forEach((t) => clearTimeout(t));
    stepTimersRef.current = [];
  };

  const handleDeleteSelected = () => {
    if (selectedIndex === null) return;
    setDrawnPoints((prev) => prev.filter((_, i) => i !== selectedIndex));
    setSelectedIndex(null);
  };

  const handleCloseModal = () => {
    clearStepTimers();
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
      abortControllerRef.current = null;
    }
    setIsFetching(false);
    setStatusMsg('');
    setCustomModalOpen(false);
  };

  // Fetch OpenStreetMap data and generate 3D WebGL context via backend engine
  const handleFetch = async () => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
    }
    clearStepTimers();
    const controller = new AbortController();
    abortControllerRef.current = controller;

    setIsFetching(true);
    setStatusMsg('Fetching OSM...');

    // Progressively update status text across real pipeline stages
    stepTimersRef.current.push(
      setTimeout(() => {
        if (!controller.signal.aborted) setStatusMsg('Processing site & roads...');
      }, 700)
    );

    stepTimersRef.current.push(
      setTimeout(() => {
        if (!controller.signal.aborted) setStatusMsg('Extruding 3D context...');
      }, 1400)
    );

    stepTimersRef.current.push(
      setTimeout(() => {
        if (!controller.signal.aborted) setStatusMsg('Saving 3D scene...');
      }, 2200)
    );

    try {
      const payload = {
        lat: selectedLat,
        lon: selectedLon,
        name: locationName || 'Custom Location',
        road_setback: roadSetback,
        building_setback: buildingSetback,
        parcel_type: parcelType,
      };
      if (selectMode === 'draw' && drawnPoints.length >= 3) {
        payload.custom_polygon = drawnPoints;
      }

      const res = await fetch('/api/fetch-custom-site', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        signal: controller.signal,
        body: JSON.stringify(payload),
      });

      clearStepTimers();

      if (!res.ok) {
        const errData = await res.json().catch(() => ({}));
        throw new Error(errData.error || `Server status ${res.status}`);
      }

      const newSiteRecord = await res.json();
      console.log('Fetched new site record:', newSiteRecord);

      addCustomSite(newSiteRecord);
      setIsFetching(false);
      setStatusMsg('');
      abortControllerRef.current = null;
      setCustomModalOpen(false);
    } catch (err) {
      clearStepTimers();
      if (err.name === 'AbortError') {
        console.log('Fetch request cancelled by user');
        return;
      }
      console.error(err);
      setStatusMsg(`Error fetching site: ${err.message || 'Failed'}`);
      setIsFetching(false);
      abortControllerRef.current = null;
    }
  };

  return (
    <div className="modal-overlay" onClick={handleCloseModal}>
      <div className="custom-site-modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <div style={{ display: 'flex', alignItems: 'center', gap: '14px' }}>
            <h3>Select Location</h3>
            <div className="mode-toggle-bar">
              <button
                type="button"
                className={`mode-toggle-btn ${selectMode === 'marker' ? 'active' : ''}`}
                onClick={() => setSelectMode('marker')}
              >
                Point Marker
              </button>
              <button
                type="button"
                className={`mode-toggle-btn ${selectMode === 'draw' ? 'active' : ''}`}
                onClick={() => setSelectMode('draw')}
              >
                Draw Parcel
              </button>
            </div>
          </div>
          <button className="btn-close-modal" onClick={handleCloseModal} title="Close window">
            &times;
          </button>
        </div>

        <form className="map-search-bar" onSubmit={handleSearch}>
          <input
            type="text"
            className="map-search-input"
            placeholder="Search any city or address (e.g. Eiffel Tower, Paris / Shibuya, Tokyo)"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
          />
          <button type="submit" className="btn-search-map">
            Search
          </button>
        </form>

        <div className={`leaflet-map-wrapper ${selectMode === 'draw' ? 'draw-mode-map' : ''}`} style={{ position: 'relative' }}>
          <div ref={mapRef} style={{ width: '100%', height: '100%' }}></div>

          {selectMode === 'marker' && (
            <div className="map-draw-toolbar">
              <div className="setback-input-group">
                <label>Building Setback (m):</label>
                <input
                  type="number"
                  step="0.5"
                  min="0"
                  max="20"
                  className="setback-num-input"
                  value={buildingSetback}
                  onChange={(e) => setBuildingSetback(parseFloat(e.target.value) || 0)}
                />
              </div>
              <div className="setback-input-group">
                <label>Road Setback (m):</label>
                <input
                  type="number"
                  step="0.5"
                  min="0"
                  max="20"
                  className="setback-num-input"
                  value={roadSetback}
                  onChange={(e) => setRoadSetback(parseFloat(e.target.value) || 0)}
                />
              </div>
            </div>
          )}

          {selectMode === 'draw' && (
            <div className="map-draw-toolbar">
              <span className="draw-status-text">
                {drawnPoints.length === 0
                  ? 'Click map to place parcel corner points'
                  : drawnPoints.length < 3
                  ? `${drawnPoints.length} point(s) placed`
                  : `Plot Area: ${drawnArea.toLocaleString()} m²`}
              </span>
              {drawnPoints.length > 0 && (
                <>
                  {selectedIndex !== null && (
                    <button
                      type="button"
                      className="btn-draw-action btn-delete-point"
                      onClick={handleDeleteSelected}
                      style={{ color: '#dc2626', fontWeight: '700' }}
                    >
                      Delete Point
                    </button>
                  )}
                  <button
                    type="button"
                    className="btn-draw-action"
                    onClick={() => {
                      setDrawnPoints((p) => p.slice(0, -1));
                      setSelectedIndex(null);
                    }}
                  >
                    Undo
                  </button>
                  <button
                    type="button"
                    className="btn-draw-action"
                    onClick={() => {
                      setDrawnPoints([]);
                      setSelectedIndex(null);
                    }}
                  >
                    Clear
                  </button>
                </>
              )}
            </div>
          )}
        </div>

        <div className="modal-footer">
          <div className="coords-summary">
            <div>Lat: {selectedLat.toFixed(6)}, Lon: {selectedLon.toFixed(6)} ({locationName})</div>
            {statusMsg && !isFetching && <div style={{ color: '#ef4444', marginTop: '2px', fontWeight: '600', fontSize: '11px' }}>{statusMsg}</div>}
          </div>

          <button
            className="btn-fetch-action"
            onClick={handleFetch}
            disabled={isFetching}
          >
            {isFetching ? (statusMsg || 'Fetching OSM...') : 'Generate Context'}
          </button>
        </div>
      </div>
    </div>
  );
};
