// ============================================================
// Globe.gl is loaded via CDN in the HTML (exposes window.Globe)
// ============================================================
const Globe = window.Globe

// ============================================================
// SHARED FILTER STATE (synced with dashboard via localStorage)
// ============================================================
const FILTER_KEY = 'notdoomsday-filters'

function getFiltersFromStorage() {
  try {
    const raw = localStorage.getItem(FILTER_KEY)
    return raw ? JSON.parse(raw) : null
  } catch { return null }
}

function saveFiltersToStorage(active) {
  localStorage.setItem(FILTER_KEY, JSON.stringify(active))
}

function getActiveCalamities() {
  return Array.from(document.querySelectorAll('.globe-filter-item input:checked'))
    .map(el => el.dataset.calamity)
}

// On load, restore filter state from localStorage
function restoreFilters() {
  const saved = getFiltersFromStorage()
  if (!saved) return // all checked by default

  document.querySelectorAll('.globe-filter-item input').forEach(el => {
    el.checked = saved.includes(el.dataset.calamity)
  })
}

// ============================================================
// CALAMITY TYPE CONFIG
// ============================================================
const CALAMITY_CONFIG = {
  volcano:    { color: '#ff4d2e', emoji: '🌋', label: 'Volcano' },
  fire:       { color: '#f97316', emoji: '🔥', label: 'Fire Hotspot' },
  earthquake: { color: '#8b5cf6', emoji: '🌍', label: 'Seismic Event' },
  flood:      { color: '#3b82f6', emoji: '🌊', label: 'Flood Zone' },
  pandemic:   { color: '#10b981', emoji: '🦠', label: 'Pandemic' },
  solar:      { color: '#fbbf24', emoji: '☀️', label: 'Solar Flare' },
}

// ============================================================
// DATA STORES
// ============================================================
let allVolcanoData = []
let allFireData = []
let allEarthquakeData = []
let allFloodData = []

// ============================================================
// DATA PARSING: shared format {"lat,lng": "Low|Medium|High"}
// ============================================================
function riskLevelToScore(level) {
  if (level === 'High') return 80
  if (level === 'Medium') return 50
  if (level === 'Low') return 20
  return 10
}

function parseCoordinateData(raw, type) {
  return Object.entries(raw).map(([coords, riskLevel]) => {
    const parts = coords.split(',').map(s => parseFloat(s.trim()))
    if (parts.length < 2 || isNaN(parts[0]) || isNaN(parts[1])) return null
    return {
      type,
      latitude: parts[0],
      longitude: parts[1],
      risk_level: riskLevel,
      composite_risk_score: riskLevelToScore(riskLevel),
      name: CALAMITY_CONFIG[type]?.label || type,
    }
  }).filter(Boolean)
}

// ============================================================
// DATA LOADING
// ============================================================
async function loadVolcanoData() {
  try {
    const resp = await fetch('./volcano_data/volcanoes_enriched.json')
    if (resp.ok) {
      const data = await resp.json()
      if (data.length > 0 && data[0].latitude) {
        console.log(`Loaded ${data.length} volcanoes from local cache`)
        return data
      }
    }
  } catch (e) {
    console.log('Local data not found, fetching from USGS...')
  }

  // Fallback: pull directly from USGS APIs
  console.log('Fetching from USGS HANS API...')
  const [allResp, monResp, elevResp] = await Promise.all([
    fetch('https://volcanoes.usgs.gov/hans-public/api/volcano/getUSVolcanoes'),
    fetch('https://volcanoes.usgs.gov/hans-public/api/volcano/getMonitoredVolcanoes'),
    fetch('https://volcanoes.usgs.gov/hans-public/api/volcano/getElevatedVolcanoes'),
  ])

  const allVolcanoes = await allResp.json()
  const monitored = await monResp.json()
  const elevated = await elevResp.json()

  const monSet = new Set(monitored.map(v => v.vnum))
  const elevMap = {}
  elevated.forEach(v => { elevMap[v.vnum] = v })

  const THREAT_SCORES = {
    'Very High Threat': 5, 'High Threat': 4, 'Moderate Threat': 3,
    'Low Threat': 2, 'Very Low Threat': 1, 'Unassigned': 0,
  }
  const ALERT_SCORES = { 'WARNING': 4, 'WATCH': 3, 'ADVISORY': 2, 'NORMAL': 1 }
  const COLOR_SCORES = { 'RED': 4, 'ORANGE': 3, 'YELLOW': 2, 'GREEN': 1 }

  return allVolcanoes.map(v => {
    const vnum = v.vnum || ''
    const elev = elevMap[vnum] || {}
    const alert = elev.alert_level || elev.alertLevel || null
    const color = elev.color_code || elev.colorCode || null
    const alertStr = alert ? String(alert).toUpperCase() : null
    const colorStr = color ? String(color).toUpperCase() : null
    const threatScore = THREAT_SCORES[v.nvews_threat] || 0
    const alertScore = ALERT_SCORES[alertStr] || 0
    const colorScore = COLOR_SCORES[colorStr] || 0
    const risk = Math.round(
      (threatScore / 5) * 25 + (alertScore / 4) * 25 + (colorScore / 4) * 15
    )
    return {
      vnum, volcano_name: v.volcano_name || '', region: v.region || '',
      latitude: v.latitude, longitude: v.longitude,
      elevation_meters: v.elevation_meters,
      is_monitored: monSet.has(vnum), nvews_threat: v.nvews_threat || 'Unassigned',
      threat_score: threatScore, alert_level: alert, color_code: color,
      alert_score: alertScore, color_score: colorScore,
      volcano_url: v.volcano_url || '', volcano_image_url: v.volcano_image_url || '',
      eq_count_30d: v.eq_count_30d || 0, eq_max_mag_30d: v.eq_max_mag_30d || 0,
      eq_shallow_count: v.eq_shallow_count || 0,
      composite_risk_score: v.composite_risk_score || risk,
    }
  }).filter(v => v.latitude && v.longitude)
}

async function loadFireData() {
  try {
    const resp = await fetch('./Data/map_fire.json')
    if (resp.ok) {
      const raw = await resp.json()
      const data = parseCoordinateData(raw, 'fire')
      console.log(`Loaded ${data.length} fire hotspots`)
      return data
    }
  } catch (e) { console.log('Fire data not available') }
  return []
}

async function loadEarthquakeData() {
  try {
    const resp = await fetch('./Data/earthquake_coordinates.json')
    if (resp.ok) {
      const raw = await resp.json()
      const data = parseCoordinateData(raw, 'earthquake')
      console.log(`Loaded ${data.length} earthquake events`)
      return data
    }
  } catch (e) { console.log('Earthquake data not available') }
  return []
}

async function loadFloodData() {
  try {
    const resp = await fetch('./Data/flood_coordinates.json')
    if (resp.ok) {
      const raw = await resp.json()
      const data = parseCoordinateData(raw, 'flood')
      console.log(`Loaded ${data.length} flood zones`)
      return data
    }
  } catch (e) { console.log('Flood data not available') }
  return []
}

// ============================================================
// COLOR / SIZING HELPERS
// ============================================================
function riskColor(score, alpha = 1) {
  if (score >= 70) return `rgba(244, 63, 94, ${alpha})`
  if (score >= 40) return `rgba(249, 115, 22, ${alpha})`
  if (score >= 15) return `rgba(234, 179, 8, ${alpha})`
  return `rgba(34, 197, 94, ${alpha})`
}

function riskColorHex(score) {
  if (score >= 70) return '#f43f5e'
  if (score >= 40) return '#f97316'
  if (score >= 15) return '#eab308'
  return '#22c55e'
}

function hexToRgba(hex, alpha) {
  const r = parseInt(hex.slice(1, 3), 16)
  const g = parseInt(hex.slice(3, 5), 16)
  const b = parseInt(hex.slice(5, 7), 16)
  return `rgba(${r},${g},${b},${alpha})`
}

// Volcano-specific sizing (preserved from original)
function volcanoPointAlt(d) {
  if (!d.is_monitored) return 0.01
  return 0.01 + (d.composite_risk_score / 100) * 0.15
}

function volcanoPointRadius(d) {
  if (!d.is_monitored) return 0.15
  if (d.alert_score >= 3) return 0.6
  if (d.alert_score >= 2) return 0.45
  return 0.25 + (d.threat_score / 5) * 0.2
}

// ============================================================
// MULTI-TYPE POINT STYLING
// ============================================================
function getPointColor(d) {
  if (d.type === 'volcano') {
    return d.is_monitored ? riskColor(d.composite_risk_score, 0.85) : 'rgba(255,255,255,0.12)'
  }
  const base = CALAMITY_CONFIG[d.type]?.color || '#ffffff'
  const alpha = d.risk_level === 'High' ? 0.95 : d.risk_level === 'Medium' ? 0.7 : 0.45
  return hexToRgba(base, alpha)
}

function getPointAltitude(d) {
  if (d.type === 'volcano') return volcanoPointAlt(d)
  return d.risk_level === 'High' ? 0.1 : d.risk_level === 'Medium' ? 0.06 : 0.03
}

function getPointRadius(d) {
  if (d.type === 'volcano') return volcanoPointRadius(d)
  return d.risk_level === 'High' ? 0.5 : d.risk_level === 'Medium' ? 0.35 : 0.25
}

function getPointLabel(d) {
  if (d.type === 'volcano') {
    return `
      <div style="font-family:'Outfit',sans-serif;background:rgba(10,12,18,0.92);backdrop-filter:blur(12px);border:1px solid rgba(255,255,255,0.1);border-radius:10px;padding:10px 14px;min-width:180px;box-shadow:0 8px 32px rgba(0,0,0,0.5);">
        <div style="font-weight:700;font-size:14px;color:#f0f2f5;margin-bottom:4px;">${d.volcano_name}</div>
        <div style="font-family:JetBrains Mono,monospace;font-size:10px;color:#5a6270;margin-bottom:8px;">${d.region}</div>
        <div style="display:flex;gap:12px;">
          <div><div style="font-family:JetBrains Mono,monospace;font-size:9px;color:#4a5060;text-transform:uppercase;letter-spacing:0.5px;">Risk</div><div style="font-size:18px;font-weight:700;color:${riskColorHex(d.composite_risk_score)};">${Math.round(d.composite_risk_score)}</div></div>
          <div><div style="font-family:JetBrains Mono,monospace;font-size:9px;color:#4a5060;text-transform:uppercase;letter-spacing:0.5px;">Alert</div><div style="font-size:13px;font-weight:600;color:#c8cdd5;margin-top:2px;">${d.alert_level || 'Normal'}</div></div>
          <div><div style="font-family:JetBrains Mono,monospace;font-size:9px;color:#4a5060;text-transform:uppercase;letter-spacing:0.5px;">EQ/30d</div><div style="font-size:13px;font-weight:600;color:#c8cdd5;margin-top:2px;">${d.eq_count_30d}</div></div>
        </div>
      </div>
    `
  }

  const config = CALAMITY_CONFIG[d.type] || { emoji: '⚠️', label: d.type, color: '#ff6840' }
  const rColor = d.risk_level === 'High' ? '#f43f5e' : d.risk_level === 'Medium' ? '#f97316' : '#22c55e'

  return `
    <div style="font-family:'Outfit',sans-serif;background:rgba(10,12,18,0.92);backdrop-filter:blur(12px);border:1px solid rgba(255,255,255,0.1);border-radius:10px;padding:10px 14px;min-width:160px;box-shadow:0 8px 32px rgba(0,0,0,0.5);">
      <div style="display:flex;align-items:center;gap:6px;margin-bottom:6px;">
        <span style="font-size:16px;">${config.emoji}</span>
        <span style="font-weight:700;font-size:14px;color:${config.color};">${config.label}</span>
      </div>
      <div style="font-family:JetBrains Mono,monospace;font-size:10px;color:#5a6270;margin-bottom:8px;">${d.latitude.toFixed(3)}°, ${d.longitude.toFixed(3)}°</div>
      <div style="display:flex;align-items:center;gap:8px;">
        <div style="width:8px;height:8px;border-radius:50%;background:${rColor};box-shadow:0 0 6px ${rColor}40;"></div>
        <span style="font-family:JetBrains Mono,monospace;font-size:13px;font-weight:600;color:${rColor};">${d.risk_level} Risk</span>
      </div>
    </div>
  `
}

// ============================================================
// UI HELPERS
// ============================================================
function updateStats(active) {
  const volcanoEnabled = active.includes('volcano')
  const fireEnabled = active.includes('fire')
  const earthquakeEnabled = active.includes('earthquake')
  const floodEnabled = active.includes('flood')

  // Total data points across all active layers
  let total = 0
  if (volcanoEnabled) total += allVolcanoData.length
  if (fireEnabled) total += allFireData.length
  if (earthquakeEnabled) total += allEarthquakeData.length
  if (floodEnabled) total += allFloodData.length
  document.getElementById('stat-total').textContent = total

  // Active layers count
  const layerCounts = []
  if (volcanoEnabled) layerCounts.push('volcano')
  if (fireEnabled) layerCounts.push('fire')
  if (earthquakeEnabled) layerCounts.push('earthquake')
  if (floodEnabled) layerCounts.push('flood')
  document.getElementById('stat-layers').textContent = layerCounts.length

  // Elevated / high risk across all active layers
  let elevated = 0
  if (volcanoEnabled) elevated += allVolcanoData.filter(d => d.alert_score >= 2).length
  if (fireEnabled) elevated += allFireData.filter(d => d.risk_level === 'High').length
  if (earthquakeEnabled) elevated += allEarthquakeData.filter(d => d.risk_level === 'High').length
  if (floodEnabled) elevated += allFloodData.filter(d => d.risk_level === 'High').length
  document.getElementById('stat-elevated').textContent = elevated
  document.getElementById('elevated-count').textContent = elevated

  // Fire hotspots count (if active)
  document.getElementById('stat-fires').textContent = fireEnabled ? allFireData.length : '—'
}

function buildAlertList(globe) {
  const container = document.getElementById('alert-list')
  const active = getActiveCalamities()
  const items = []

  // Volcano alerts (top by risk score)
  if (active.includes('volcano')) {
    allVolcanoData
      .filter(d => d.is_monitored)
      .sort((a, b) => b.composite_risk_score - a.composite_risk_score)
      .slice(0, 8)
      .forEach(v => {
        const colorClass = v.color_code ? String(v.color_code).toUpperCase() : 'GREEN'
        items.push({
          type: 'volcano',
          name: v.volcano_name,
          meta: `${v.region} · ${v.alert_level || 'Normal'} · ${v.eq_count_30d} eq/30d`,
          risk: Math.round(v.composite_risk_score),
          colorClass,
          lat: v.latitude,
          lng: v.longitude,
          data: v,
        })
      })
  }

  // Fire alerts
  if (active.includes('fire')) {
    allFireData
      .sort((a, b) => b.composite_risk_score - a.composite_risk_score)
      .slice(0, 4)
      .forEach(d => {
        items.push({
          type: 'fire',
          name: '🔥 Fire Hotspot',
          meta: `${d.latitude.toFixed(2)}°, ${d.longitude.toFixed(2)}° · ${d.risk_level}`,
          risk: d.composite_risk_score,
          colorClass: d.risk_level === 'High' ? 'ORANGE' : 'GREEN',
          lat: d.latitude,
          lng: d.longitude,
          data: d,
        })
      })
  }

  // Earthquake alerts
  if (active.includes('earthquake')) {
    allEarthquakeData
      .sort((a, b) => b.composite_risk_score - a.composite_risk_score)
      .slice(0, 4)
      .forEach(d => {
        items.push({
          type: 'earthquake',
          name: '🌍 Seismic Event',
          meta: `${d.latitude.toFixed(2)}°, ${d.longitude.toFixed(2)}° · ${d.risk_level}`,
          risk: d.composite_risk_score,
          colorClass: d.risk_level === 'High' ? 'RED' : d.risk_level === 'Medium' ? 'YELLOW' : 'GREEN',
          lat: d.latitude,
          lng: d.longitude,
          data: d,
        })
      })
  }

  // Flood alerts
  if (active.includes('flood')) {
    allFloodData
      .sort((a, b) => b.composite_risk_score - a.composite_risk_score)
      .slice(0, 4)
      .forEach(d => {
        items.push({
          type: 'flood',
          name: '🌊 Flood Zone',
          meta: `${d.latitude.toFixed(2)}°, ${d.longitude.toFixed(2)}° · ${d.risk_level}`,
          risk: d.composite_risk_score,
          colorClass: d.risk_level === 'High' ? 'RED' : d.risk_level === 'Medium' ? 'YELLOW' : 'GREEN',
          lat: d.latitude,
          lng: d.longitude,
          data: d,
        })
      })
  }

  // Sort by risk descending, take top 12
  items.sort((a, b) => b.risk - a.risk)
  const top = items.slice(0, 12)

  if (top.length === 0) {
    container.innerHTML = '<div style="font-size:12px;color:#5a6270;padding:8px;">No active data layers</div>'
    return
  }

  container.innerHTML = top.map((item, i) => `
    <div class="alert-item" data-idx="${i}">
      <div class="alert-color-badge ${item.colorClass}"></div>
      <div>
        <div class="alert-name">${item.name}</div>
        <div class="alert-meta">${item.meta}</div>
      </div>
      <div class="alert-risk">${item.risk}</div>
    </div>
  `).join('')

  container.querySelectorAll('.alert-item').forEach((el) => {
    el.addEventListener('click', () => {
      const idx = parseInt(el.dataset.idx)
      const item = top[idx]
      if (item) {
        if (item.type === 'volcano') {
          showVolcanoDetail(item.data)
        } else {
          showGenericDetail(item.data)
        }
        globe.pointOfView({ lat: item.lat, lng: item.lng, altitude: 1.5 }, 1200)
      }
    })
  })
}

// ============================================================
// DETAIL PANELS
// ============================================================
function showVolcanoDetail(v) {
  const panel = document.getElementById('detail-panel')
  panel.classList.add('visible')

  document.getElementById('d-name').textContent = v.volcano_name
  document.getElementById('d-region').textContent =
    `${v.region} · ${v.latitude.toFixed(3)}°, ${v.longitude.toFixed(3)}°`

  const risk = Math.round(v.composite_risk_score)
  const riskEl = document.getElementById('d-risk')
  riskEl.textContent = `${risk}/100`
  riskEl.className = 'detail-stat-value ' + (risk >= 70 ? 'danger' : risk >= 40 ? 'warning' : 'ok')

  document.getElementById('d-risk-bar').style.width = `${risk}%`
  document.getElementById('d-risk-bar').style.background = riskColorHex(risk)

  const alertEl = document.getElementById('d-alert')
  alertEl.textContent = v.alert_level || 'NORMAL'
  alertEl.className = 'detail-stat-value ' + (v.alert_score >= 3 ? 'danger' : v.alert_score >= 2 ? 'warning' : 'ok')

  document.getElementById('d-color').textContent = v.color_code || 'GREEN'
  document.getElementById('d-threat').textContent = v.nvews_threat.replace(' Threat', '')
  document.getElementById('d-eq').textContent = v.eq_count_30d || '0'
  document.getElementById('d-mag').textContent = v.eq_max_mag_30d ? `M${v.eq_max_mag_30d}` : '—'
  document.getElementById('d-shallow').textContent = v.eq_shallow_count || '0'
  document.getElementById('d-elev').textContent = v.elevation_meters ? `${v.elevation_meters}m` : '—'

  const link = document.getElementById('d-link')
  link.href = v.volcano_url || '#'
  link.style.display = v.volcano_url ? 'inline-block' : 'none'
}

function showGenericDetail(d) {
  const panel = document.getElementById('detail-panel')
  panel.classList.add('visible')

  const config = CALAMITY_CONFIG[d.type] || {}

  document.getElementById('d-name').textContent = `${config.emoji || ''} ${config.label || d.type}`
  document.getElementById('d-region').textContent = `${d.latitude.toFixed(4)}°, ${d.longitude.toFixed(4)}°`

  const risk = d.composite_risk_score
  const riskEl = document.getElementById('d-risk')
  riskEl.textContent = `${risk}/100`
  riskEl.className = 'detail-stat-value ' + (risk >= 70 ? 'danger' : risk >= 40 ? 'warning' : 'ok')

  document.getElementById('d-risk-bar').style.width = `${risk}%`
  document.getElementById('d-risk-bar').style.background = config.color || '#ff6840'

  const alertEl = document.getElementById('d-alert')
  alertEl.textContent = d.risk_level
  alertEl.className = 'detail-stat-value ' + (d.risk_level === 'High' ? 'danger' : d.risk_level === 'Medium' ? 'warning' : 'ok')

  document.getElementById('d-color').textContent = '—'
  document.getElementById('d-threat').textContent = d.risk_level
  document.getElementById('d-eq').textContent = '—'
  document.getElementById('d-mag').textContent = '—'
  document.getElementById('d-shallow').textContent = '—'
  document.getElementById('d-elev').textContent = '—'

  document.getElementById('d-link').style.display = 'none'
}

function hideDetail() {
  document.getElementById('detail-panel').classList.remove('visible')
}

// Clock
function updateClock() {
  const el = document.getElementById('utc-time')
  if (el) el.textContent = new Date().toISOString().slice(11, 19)
}
setInterval(updateClock, 1000)
updateClock()

// ============================================================
// GLOBE SETUP
// ============================================================
let globe

async function init() {
  // Load all data layers in parallel
  const [volcanoes, fires, earthquakes, floods] = await Promise.all([
    loadVolcanoData(),
    loadFireData(),
    loadEarthquakeData(),
    loadFloodData(),
  ])

  // Store with type tags
  allVolcanoData = volcanoes.map(d => ({ ...d, type: 'volcano' }))
  allFireData = fires
  allEarthquakeData = earthquakes
  allFloodData = floods

  console.log(`Data loaded — Volcanoes: ${allVolcanoData.length}, Fire: ${allFireData.length}, Earthquake: ${allEarthquakeData.length}, Flood: ${allFloodData.length}`)

  restoreFilters()
  applyFilters()
}

function applyFilters() {
  const active = getActiveCalamities()
  saveFiltersToStorage(active)

  // Build merged points from all active layers
  const points = []
  if (active.includes('volcano')) points.push(...allVolcanoData)
  if (active.includes('fire')) points.push(...allFireData)
  if (active.includes('earthquake')) points.push(...allEarthquakeData)
  if (active.includes('flood')) points.push(...allFloodData)

  // Volcano-specific rings (pulsing for elevated)
  const elevated = active.includes('volcano')
    ? allVolcanoData.filter(d => d.alert_score >= 2)
    : []

  // Alert panel visibility
  const alertPanel = document.getElementById('alert-panel')
  if (alertPanel) alertPanel.style.display = points.length > 0 ? '' : 'none'

  if (!globe) {
    // First init
    globe = Globe()
      (document.getElementById('globe-container'))
      .globeImageUrl('//unpkg.com/three-globe/example/img/earth-night.jpg')
      .bumpImageUrl('//unpkg.com/three-globe/example/img/earth-topology.png')
      .backgroundImageUrl('//unpkg.com/three-globe/example/img/night-sky.png')
      .showAtmosphere(true)
      // .atmosphereColor('#ff2020')
      .atmosphereColor('#3a86ff')
      .atmosphereAltitude(0.18)
      .pointsData(points)
      .pointLat('latitude')
      .pointLng('longitude')
      .pointColor(d => getPointColor(d))
      .pointAltitude(d => getPointAltitude(d))
      .pointRadius(d => getPointRadius(d))
      .pointLabel(d => getPointLabel(d))
      .onPointClick(d => {
        if (d.type === 'volcano') {
          showVolcanoDetail(d)
        } else {
          showGenericDetail(d)
        }
        globe.pointOfView({ lat: d.latitude, lng: d.longitude, altitude: 1.2 }, 1000)
      })
      .ringsData(elevated)
      .ringLat('latitude')
      .ringLng('longitude')
      .ringColor(d => t => {
        const c = d.alert_score >= 3 ? '244,63,94' : '249,115,22'
        return `rgba(${c},${1 - t})`
      })
      .ringMaxRadius(d => d.alert_score >= 3 ? 5 : 3)
      .ringPropagationSpeed(d => d.alert_score >= 3 ? 3 : 2)
      .ringRepeatPeriod(d => d.alert_score >= 3 ? 600 : 1000)
      .width(window.innerWidth)
      .height(window.innerHeight)

    globe.controls().autoRotate = false
    globe.controls().autoRotateSpeed = 0.4
    globe.controls().enableDamping = true
    globe.pointOfView({ lat: 20, lng: -155, altitude: 2.5 })
  } else {
    // Update existing globe layers
    globe.pointsData(points)
    globe.ringsData(elevated)
  }

  updateStats(active)
  buildAlertList(globe)

  // Hide loading
  setTimeout(() => {
    const loading = document.getElementById('loading')
    if (loading) loading.classList.add('hidden')
  }, 800)
}

// ============================================================
// EVENT HANDLERS
// ============================================================
document.getElementById('detail-close').addEventListener('click', hideDetail)

// Calamity filter toggles on the globe page
document.querySelectorAll('.globe-filter-item input').forEach(el => {
  el.addEventListener('change', () => {
    applyFilters()
  })
})

// Resize
window.addEventListener('resize', () => {
  if (globe) {
    globe.width(window.innerWidth)
    globe.height(window.innerHeight)
  }
})

// Go!
init()
