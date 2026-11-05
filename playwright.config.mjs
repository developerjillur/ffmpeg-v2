import {defineConfig,devices} from '@playwright/test';
export default defineConfig({
  testDir:'./site/tests',fullyParallel:false,workers:1,timeout:30000,retries:0,
  reporter:[['list'],['html',{open:'never'}]],
  use:{baseURL:process.env.LIVE_SITE_URL||'http://127.0.0.1:4173/ffmpeg-v2/',trace:'retain-on-failure'},
  projects:[{name:'desktop',use:{viewport:{width:1440,height:1000}}},
    {name:'mobile',use:{...devices['iPhone 13'],defaultBrowserType:'chromium'}},
    {name:'reduced-motion',use:{viewport:{width:1280,height:900},reducedMotion:'reduce'}}],
  webServer:process.env.LIVE_SITE_URL?undefined:{command:'npm run preview',url:'http://127.0.0.1:4173/ffmpeg-v2/',reuseExistingServer:!process.env.CI}
});
