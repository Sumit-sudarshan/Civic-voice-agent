import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [
    react(),
    {
      name: 'log-routes',
      configureServer(server) {
        server.httpServer?.once('listening', () => {
          setTimeout(() => {
            const port = server.config.server.port || 5173;
            console.log('\n   Citizen Voice Form:  http://localhost:' + port + '/');
            console.log('   Leader Dashboard:     http://localhost:' + port + '/dashboard\n');
          }, 100);
        });
      }
    }
  ],
})
