import { createApp } from 'vue'
import ElSegmented from 'element-plus/es/components/segmented/index'
import ElSwitch from 'element-plus/es/components/switch/index'
import 'element-plus/theme-chalk/base.css'
import 'element-plus/theme-chalk/el-segmented.css'
import 'element-plus/theme-chalk/el-switch.css'
import 'element-plus/theme-chalk/el-message.css'
import 'element-plus/theme-chalk/el-tour.css'
import './styles.css'
import App from './App.vue'

// 只注册工作台首屏实际使用的基础控件，避免 Element Plus 全量插件进入初始包。
createApp(App)
  .component('ElSegmented', ElSegmented)
  .component('ElSwitch', ElSwitch)
  .mount('#app')
