import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import path from 'path';
import fs from 'fs';
import { exec } from 'child_process';

const fetchPlugin = () => ({
  name: 'fetch-custom-site-api',
  configureServer(server) {
    const handleFetchRequest = (req, res, next) => {
      if (req.method === 'POST') {
        let body = '';
        req.on('data', (chunk) => { body += chunk; });
        req.on('end', () => {
          try {
            const { lat, lon, name, custom_polygon, road_setback, building_setback, parcel_type } = JSON.parse(body);
            const scriptPath = path.resolve(__dirname, '../fetch_custom_site.py');
            const venvPython = path.resolve(__dirname, '../../.venv/bin/python');
            const pythonCmd = fs.existsSync(venvPython) ? venvPython : 'python3';
            const safeName = (name || 'Custom Location').replace(/"/g, '\\"');
            let polyArg = '';
            if (Array.isArray(custom_polygon) && custom_polygon.length >= 3) {
              polyArg = ` --polygon '${JSON.stringify(custom_polygon)}'`;
            }
            const rSetback = road_setback !== undefined ? parseFloat(road_setback) : 2.0;
            const bSetback = building_setback !== undefined ? parseFloat(building_setback) : 3.0;
            const pType = parcel_type === 'voronoi' ? 'voronoi' : 'convex_hull';
            const cmd = `"${pythonCmd}" "${scriptPath}" --lat ${lat} --lon ${lon} --name "${safeName}" --road-setback ${rSetback} --building-setback ${bSetback} --parcel-type ${pType}${polyArg}`;

            console.log(`[Vite Fetch API] Executing: ${cmd}`);

            exec(cmd, { cwd: path.resolve(__dirname, '..') }, (error, stdout, stderr) => {
              if (error) {
                console.error('[Vite Fetch API Error]:', stderr || error.message);
                res.statusCode = 500;
                res.setHeader('Content-Type', 'application/json');
                res.end(JSON.stringify({ error: stderr || error.message }));
                return;
              }
              try {
                const lines = stdout.trim().split('\n');
                const jsonLine = lines[lines.length - 1];
                const data = JSON.parse(jsonLine);
                res.setHeader('Content-Type', 'application/json');
                res.end(JSON.stringify(data));
              } catch (e) {
                console.error('[Vite Fetch API Parse Error]:', stdout);
                res.statusCode = 500;
                res.setHeader('Content-Type', 'application/json');
                res.end(JSON.stringify({ error: 'Failed to parse fetcher JSON output' }));
              }
            });
          } catch (err) {
            res.statusCode = 400;
            res.setHeader('Content-Type', 'application/json');
            res.end(JSON.stringify({ error: 'Invalid JSON payload' }));
          }
        });
      } else {
        next();
      }
    };

    const handleDeleteRequest = (req, res, next) => {
      if (req.method === 'POST') {
        let body = '';
        req.on('data', (chunk) => { body += chunk; });
        req.on('end', () => {
          try {
            const { site_id } = JSON.parse(body);
            if (!site_id) {
              res.statusCode = 400;
              res.setHeader('Content-Type', 'application/json');
              res.end(JSON.stringify({ error: 'Missing site_id' }));
              return;
            }

            const scriptPath = path.resolve(__dirname, '../delete_custom_site.py');
            const venvPython = path.resolve(__dirname, '../../.venv/bin/python');
            const pythonCmd = fs.existsSync(venvPython) ? venvPython : 'python3';
            const cmd = `"${pythonCmd}" "${scriptPath}" --site_id "${site_id}"`;

            console.log(`[Vite Delete API] Executing: ${cmd}`);

            exec(cmd, { cwd: path.resolve(__dirname, '..') }, (error, stdout, stderr) => {
              if (error) {
                console.error('[Vite Delete API Error]:', stderr || error.message);
                res.statusCode = 500;
                res.setHeader('Content-Type', 'application/json');
                res.end(JSON.stringify({ error: stderr || error.message }));
                return;
              }
              try {
                const data = JSON.parse(stdout.trim());
                res.setHeader('Content-Type', 'application/json');
                res.end(JSON.stringify(data));
              } catch (e) {
                res.setHeader('Content-Type', 'application/json');
                res.end(JSON.stringify({ success: true, site_id }));
              }
            });
          } catch (err) {
            res.statusCode = 400;
            res.setHeader('Content-Type', 'application/json');
            res.end(JSON.stringify({ error: 'Invalid JSON payload' }));
          }
        });
      } else {
        next();
      }
    };

    server.middlewares.use('/api/fetch-custom-site', handleFetchRequest);
    server.middlewares.use('/api/harvest-custom-site', handleFetchRequest);
    server.middlewares.use('/api/delete-custom-site', handleDeleteRequest);
  },
});

export default defineConfig({
  plugins: [react(), fetchPlugin()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  server: {
    port: 5173,
    host: true,
    allowedHosts: true,
    open: false,
    fs: {
      strict: false,
      allow: ['..'],
    },
  },
});
