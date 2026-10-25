import { defaultConfig, type AppConfig } from './config';
import { App } from './ui/app';
import './style.css';

const cfg: AppConfig = { ...defaultConfig };

const root = document.getElementById('app');
if (!root) {
  throw new Error('#app が見つかりません');
}
new App(root, cfg).showStart();
