import {defineConfig} from 'vite';
import vue from '@vitejs/plugin-vue';

const target = process.env.QUEEZO_PROXY_TARGET || 'http://localhost:8080';
const proxy = Object.fromEntries(['/api','/gwa/','/docs','/redoc','/openapi.json'].map(path => [path,{target}]));
export default defineConfig({plugins:[vue()], server:{proxy}, preview:{proxy}});
