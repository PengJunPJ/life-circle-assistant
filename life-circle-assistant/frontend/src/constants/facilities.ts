export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000'

export const FACILITY_LABELS: Record<string, string> = {
  market: '菜市场',
  pharmacy: '药店',
  school: '小学',
  medical: '医疗服务',
}

export const FACILITY_ICONS: Record<string, string> = {
  market: '菜',
  pharmacy: '药',
  school: '学',
  medical: '医',
}

export const FACILITY_COLORS: Record<string, string> = {
  market: '#e38b45',
  pharmacy: '#d65a5a',
  school: '#3d83b8',
  medical: '#3e9b8b',
}

export const DEFAULT_CATEGORIES = Object.keys(FACILITY_LABELS)
export const DEFAULT_CENTER = { lng: 113.4872, lat: 23.1068 }
// 步行路线预览色：浅绿芯线 + 深绿描边，靠"实线+描边+箭头"与等时圈青绿虚线区分
export const ROUTE_COLOR = '#74d178'
export const ROUTE_BORDER = '#2f9e44'
// 方向箭头的像素间距，越小越密
export const ROUTE_ARROW_SPACING = 30

export function categoryColor(category: string) {
  return FACILITY_COLORS[category] || '#71838a'
}

export function categoryShort(category: string) {
  return FACILITY_ICONS[category] || '?'
}
