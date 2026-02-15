import * as THREE from 'three'
import earthVertexShader from './shaders/earth/vertex.glsl'
import earthFragmentShader from './shaders/earth/fragment.glsl'
import atmosphereVertexShader from './shaders/atmosphere/vertex.glsl'
import atmosphereFragmentShader from './shaders/atmosphere/fragment.glsl'

// ============================================================
// SHARED FILTER STATE (synced with globe via localStorage)
// ============================================================
const FILTER_KEY = 'notdoomsday-filters'

function saveFiltersToStorage() {
  const active = getActiveCalamities()
  localStorage.setItem(FILTER_KEY, JSON.stringify(active))
}

function restoreFiltersFromStorage() {
  try {
    const raw = localStorage.getItem(FILTER_KEY)
    if (!raw) return
    const saved = JSON.parse(raw)
    document.querySelectorAll('.filter-item input').forEach(el => {
      el.checked = saved.includes(el.dataset.calamity)
    })
  } catch { /* ignore */ }
}

// ============================================================
// CITY DATA (volcano data enhanced from real pipeline output)
// ============================================================
const CITIES = [
  {
    name: 'Seattle', fullName: 'Seattle, WA', region: 'Washington, United States',
    lat: 47.606, lon: -122.332,
    risks: {
      volcano:    { score: 58, detail: 'Nearest: Mt. Rainier (87 km) · Alert: NORMAL · Threat: Very High' },
      earthquake: { score: 65, detail: 'Zone: Cascadia Subduction · Recent: M3.2 (12d ago) · Fault: Seattle' },
      flood:      { score: 32, detail: 'Basin: Puget Sound · Precip: 152mm/mo · Risk: Moderate' },
      fire:       { score: 18, detail: 'FWI: Low · Cover: Temperate rainforest · Season: Jul-Sep' },
      pandemic:   { score: 22, detail: 'Activity: Low · Vaccination: 79% · Beds: 2.4/1000' },
      solar:      { score: 15, detail: 'Grid: Modern · Latitude: 47.6°N · Vulnerability: Moderate' },
    },
    mitigation: [
      'Mt. Rainier lahar evacuation routes established for all valleys',
      'ShakeAlert earthquake early warning system active across WA',
      'FEMA flood insurance programs cover 12,000+ properties',
    ],
  },
  {
    name: 'Hilo', fullName: 'Hilo, HI', region: 'Hawaii, United States',
    lat: 19.721, lon: -155.084,
    risks: {
      volcano:    { score: 92, detail: 'Nearest: Kīlauea (32 km) · Alert: WATCH · Threat: Very High' },
      earthquake: { score: 72, detail: 'Zone: Hawaiian Hotspot · Recent: M4.1 (3d ago) · 367 eq/30d' },
      flood:      { score: 45, detail: 'Basin: Wailuku River · Precip: 330mm/mo · Risk: High' },
      fire:       { score: 12, detail: 'FWI: Low · Cover: Tropical forest · Risk: Low' },
      pandemic:   { score: 16, detail: 'Activity: Low · Vaccination: 74% · Beds: 1.8/1000' },
      solar:      { score: 8, detail: 'Grid: Island isolated · Latitude: 19.7°N · Vulnerability: Low' },
    },
    mitigation: [
      'HVO monitors Kīlauea 24/7 with real-time seismic network',
      'Lava flow evacuation zones mapped and signed',
      'Tsunami warning sirens tested monthly along coast',
    ],
  },
  {
    name: 'Anchorage', fullName: 'Anchorage, AK', region: 'Alaska, United States',
    lat: 61.217, lon: -149.900,
    risks: {
      volcano:    { score: 48, detail: 'Nearest: Mt. Spurr (125 km) · Alert: NORMAL · Threat: High' },
      earthquake: { score: 78, detail: 'Zone: Pacific Ring of Fire · Recent: M5.1 (8d ago) · Very active' },
      flood:      { score: 25, detail: 'Basin: Cook Inlet · Precip: 42mm/mo · Risk: Low-Moderate' },
      fire:       { score: 28, detail: 'FWI: Moderate · Cover: Boreal forest · Season: Jun-Aug' },
      pandemic:   { score: 14, detail: 'Activity: Minimal · Vaccination: 68% · Beds: 2.1/1000' },
      solar:      { score: 35, detail: 'Grid: Vulnerable · Latitude: 61.2°N · Aurora zone: High risk' },
    },
    mitigation: [
      'AVO provides 24/7 monitoring of 52 historically active volcanoes',
      'Building codes enforce M9.2 earthquake resilience standards',
      'Northern latitude increases geomagnetic storm exposure',
    ],
  },
  {
    name: 'San Francisco', fullName: 'San Francisco, CA', region: 'California, United States',
    lat: 37.775, lon: -122.419,
    risks: {
      volcano:    { score: 12, detail: 'Nearest: Clear Lake (145 km) · Alert: NORMAL · Threat: Moderate' },
      earthquake: { score: 82, detail: 'Zone: San Andreas Fault · Recent: M2.8 (5d ago) · Very High risk' },
      flood:      { score: 38, detail: 'Basin: SF Bay · Sea level rise: Critical · Storm surge risk' },
      fire:       { score: 42, detail: 'FWI: High · Cover: Chaparral/Urban · Recent: 2020 complex fires' },
      pandemic:   { score: 20, detail: 'Activity: Low · Vaccination: 85% · Beds: 2.8/1000' },
      solar:      { score: 14, detail: 'Grid: Modern CA grid · Latitude: 37.8°N · Vulnerability: Low' },
    },
    mitigation: [
      'USGS Hayward Fault retrofit program covers critical infrastructure',
      'Cal Fire stations pre-positioned for wildfire season',
      'Sea level rise adaptation plan in effect through 2050',
    ],
  },
  {
    name: 'Portland', fullName: 'Portland, OR', region: 'Oregon, United States',
    lat: 45.505, lon: -122.675,
    risks: {
      volcano:    { score: 45, detail: 'Nearest: Mt. Hood (80 km) · Alert: NORMAL · Threat: Very High' },
      earthquake: { score: 55, detail: 'Zone: Cascadia Subduction · Recent: M2.1 (18d ago) · High risk' },
      flood:      { score: 40, detail: 'Basin: Willamette/Columbia · Precip: 112mm/mo · Risk: Moderate' },
      fire:       { score: 35, detail: 'FWI: Moderate · Cover: Mixed forest · Recent: 2020 Labor Day' },
      pandemic:   { score: 18, detail: 'Activity: Low · Vaccination: 76% · Beds: 2.2/1000' },
      solar:      { score: 12, detail: 'Grid: Pacific NW grid · Latitude: 45.5°N · Vulnerability: Low' },
    },
    mitigation: [
      'Mt. Hood lahar hazard zones identified and mapped',
      'Cascadia earthquake preparedness drills held annually',
      'Columbia River flood management system operational',
    ],
  },
  {
    name: 'Los Angeles', fullName: 'Los Angeles, CA', region: 'California, United States',
    lat: 34.052, lon: -118.244,
    risks: {
      volcano:    { score: 8, detail: 'Nearest: none within 200km · Risk: Minimal' },
      earthquake: { score: 75, detail: 'Zone: San Andreas/Puente Hills · Recent: M3.5 (7d ago) · High' },
      flood:      { score: 28, detail: 'Basin: LA River · Flash flood risk · Debris flows from burn scars' },
      fire:       { score: 68, detail: 'FWI: Very High · Cover: Chaparral · Santa Ana winds critical' },
      pandemic:   { score: 25, detail: 'Activity: Low · Vaccination: 77% · Beds: 2.0/1000' },
      solar:      { score: 10, detail: 'Grid: CA independent · Latitude: 34.1°N · Vulnerability: Low' },
    },
    mitigation: [
      'Earthquake retrofit programs mandatory for older buildings',
      'Fire break zones and evacuation routes for WUI areas',
      'LA County emergency preparedness network covers 10M residents',
    ],
  },
  {
    name: 'Miami', fullName: 'Miami, FL', region: 'Florida, United States',
    lat: 25.762, lon: -80.192,
    risks: {
      volcano:    { score: 0, detail: 'No volcanic risk · Nearest: none' },
      earthquake: { score: 5, detail: 'Zone: Stable platform · Risk: Very Low' },
      flood:      { score: 78, detail: 'Basin: Biscayne Bay · Sea level: Critical · Hurricane surge zone' },
      fire:       { score: 15, detail: 'FWI: Low-Moderate · Cover: Subtropical · Everglades fires seasonal' },
      pandemic:   { score: 35, detail: 'Activity: Moderate · Vaccination: 71% · Port of entry risk' },
      solar:      { score: 8, detail: 'Grid: FPL network · Latitude: 25.8°N · Vulnerability: Low' },
    },
    mitigation: [
      'Hurricane evacuation zones A-E mapped for all of Miami-Dade',
      'NOAA storm surge modeling covers entire Florida coastline',
      'Miami-Dade sea level rise task force active since 2019',
    ],
  },
  {
    name: 'Honolulu', fullName: 'Honolulu, HI', region: 'Hawaii, United States',
    lat: 21.307, lon: -157.858,
    risks: {
      volcano:    { score: 25, detail: 'Nearest: Diamond Head (extinct) · Mauna Loa (320 km) · Low direct risk' },
      earthquake: { score: 30, detail: 'Zone: Hawaiian Hotspot · Recent: M2.1 (22d ago) · Moderate' },
      flood:      { score: 52, detail: 'Basin: Coastal · Tsunami risk: High · Hurricane lane' },
      fire:       { score: 20, detail: 'FWI: Moderate · Cover: Urban/Grassland · Maui 2023 precedent' },
      pandemic:   { score: 18, detail: 'Activity: Low · Vaccination: 82% · Island isolation factor' },
      solar:      { score: 6, detail: 'Grid: Island isolated · Latitude: 21.3°N · Vulnerability: Low' },
    },
    mitigation: [
      'Pacific Tsunami Warning Center HQ located on Oahu',
      'Hurricane shelters designated across all islands',
      'Wildfire prevention protocols updated post-Maui 2023',
    ],
  },
  {
    name: 'Denver', fullName: 'Denver, CO', region: 'Colorado, United States',
    lat: 39.739, lon: -104.990,
    risks: {
      volcano:    { score: 2, detail: 'Nearest: Dotsero (190 km) · Last eruption: 4,200 years ago · Minimal' },
      earthquake: { score: 18, detail: 'Zone: Stable interior · Recent: M1.8 (45d ago) · Low risk' },
      flood:      { score: 30, detail: 'Basin: South Platte · Flash flood: Moderate · Snowmelt seasonal' },
      fire:       { score: 55, detail: 'FWI: High · Cover: Pine/Grassland · WUI expansion critical' },
      pandemic:   { score: 15, detail: 'Activity: Low · Vaccination: 73% · Beds: 2.5/1000' },
      solar:      { score: 20, detail: 'Grid: Western Interconnect · Latitude: 39.7°N · Moderate' },
    },
    mitigation: [
      'Colorado wildfire risk maps updated annually for WUI zones',
      'Flash flood warning system active for Front Range canyons',
      'NOAA Space Weather Prediction Center located in Boulder',
    ],
  },
  {
    name: 'New York', fullName: 'New York, NY', region: 'New York, United States',
    lat: 40.713, lon: -74.006,
    risks: {
      volcano:    { score: 0, detail: 'No volcanic risk · Nearest: none' },
      earthquake: { score: 15, detail: 'Zone: Ramapo Fault · Recent: M2.0 (60d ago) · Low risk' },
      flood:      { score: 62, detail: 'Basin: Hudson/Coastal · Storm surge: High · Sandy precedent' },
      fire:       { score: 5, detail: 'FWI: Very Low · Cover: Urban · Risk: Minimal' },
      pandemic:   { score: 42, detail: 'Activity: Moderate · Vaccination: 80% · Hub: Very high density' },
      solar:      { score: 22, detail: 'Grid: Dense NE grid · Latitude: 40.7°N · Infrastructure: Aging' },
    },
    mitigation: [
      'Hurricane Sandy resilience upgrades completed for Lower Manhattan',
      'NYC pandemic response infrastructure upgraded post-2020',
      'Flood insurance requirements for 400,000+ properties',
    ],
  },
]

// ============================================================
// CALAMITY DEFINITIONS
// ============================================================
const CALAMITIES = {
  volcano:    { name: 'Volcano',      icon: '🌋', color: '#ff4d2e' },
  earthquake: { name: 'Earthquake',   icon: '🌍', color: '#8b5cf6' },
  flood:      { name: 'Flood',        icon: '🌊', color: '#3b82f6' },
  fire:       { name: 'Forest Fire',  icon: '🔥', color: '#f97316' },
  pandemic:   { name: 'Pandemic',     icon: '🦠', color: '#10b981' },
  solar:      { name: 'Solar Flare',  icon: '☀️', color: '#fbbf24' },
}

// ============================================================
// HELPERS
// ============================================================
function scoreColor(score) {
  if (score >= 70) return '#f43f5e'
  if (score >= 50) return '#f97316'
  if (score >= 30) return '#eab308'
  return '#22c55e'
}

function threatLevel(score) {
  if (score >= 80) return { text: 'CRITICAL', css: 'color-critical' }
  if (score >= 60) return { text: 'ELEVATED', css: 'color-high' }
  if (score >= 40) return { text: 'MODERATE', css: 'color-moderate' }
  if (score >= 20) return { text: 'LOW', css: 'color-low' }
  return { text: 'MINIMAL', css: 'color-minimal' }
}

function threatDesc(level) {
  const descs = {
    CRITICAL: 'Immediate risk factors detected. Multiple high-severity threats within monitoring radius. Stay alert.',
    ELEVATED: 'Multiple active risk factors detected. Monitoring systems engaged across threat categories.',
    MODERATE: 'Some risk factors present. Monitoring systems tracking activity within normal parameters.',
    LOW: 'Minimal active threats detected. Standard monitoring protocols in effect.',
    MINIMAL: 'No significant threats detected. All systems nominal.',
  }
  return descs[level] || descs.LOW
}

// ============================================================
// VOLCANO DATA (from pipeline, merged at runtime)
// ============================================================
let volcanoData = []

async function loadVolcanoData() {
  try {
    const resp = await fetch('./volcano_data/volcanoes_enriched.json')
    if (resp.ok) {
      volcanoData = await resp.json()
      console.log(`Loaded ${volcanoData.length} volcanoes from pipeline`)
    }
  } catch (e) {
    console.log('Volcano data not available, using defaults')
  }
}

function haversine(lat1, lon1, lat2, lon2) {
  const R = 6371
  const dLat = (lat2 - lat1) * Math.PI / 180
  const dLon = (lon2 - lon1) * Math.PI / 180
  const a = Math.sin(dLat / 2) ** 2 +
    Math.cos(lat1 * Math.PI / 180) * Math.cos(lat2 * Math.PI / 180) *
    Math.sin(dLon / 2) ** 2
  return R * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a))
}

function getNearbyVolcanoes(lat, lon, radiusKm = 300) {
  return volcanoData
    .filter(v => v.latitude && v.longitude)
    .map(v => ({
      ...v,
      distance: Math.round(haversine(lat, lon, v.latitude, v.longitude)),
    }))
    .filter(v => v.distance <= radiusKm)
    .sort((a, b) => a.distance - b.distance)
    .slice(0, 5)
}

// ============================================================
// POPULATE CITY DROPDOWN
// ============================================================
const citySelect = document.getElementById('city-select')

CITIES.forEach((city, i) => {
  const opt = document.createElement('option')
  opt.value = i
  opt.textContent = city.fullName
  citySelect.appendChild(opt)
})

// ============================================================
// APO-DEX RENDERING
// ============================================================
let currentCityIndex = 0

function getActiveCalamities() {
  return Array.from(document.querySelectorAll('.filter-item input:checked'))
    .map(el => el.dataset.calamity)
}

function renderApoDex() {
  const city = CITIES[currentCityIndex]
  const active = getActiveCalamities()

  // Scan animation
  const screen = document.querySelector('.apodex-screen')
  screen.classList.remove('scanning')
  void screen.offsetWidth // reflow
  screen.classList.add('scanning')
  setTimeout(() => screen.classList.remove('scanning'), 600)

  // Entry ID
  document.getElementById('entry-id').textContent =
    `#${String(currentCityIndex + 1).padStart(3, '0')}`

  // City info
  document.getElementById('city-name').textContent = city.name.toUpperCase()
  document.getElementById('city-region').textContent = city.region
  const latDir = city.lat >= 0 ? 'N' : 'S'
  const lonDir = city.lon >= 0 ? 'E' : 'W'
  document.getElementById('city-coords').textContent =
    `${Math.abs(city.lat).toFixed(3)}°${latDir} · ${Math.abs(city.lon).toFixed(3)}°${lonDir}`

  // Composite threat index (average of active calamities)
  const activeRisks = active
    .map(key => city.risks[key]?.score ?? 0)
  const composite = activeRisks.length > 0
    ? Math.round(activeRisks.reduce((a, b) => a + b, 0) / activeRisks.length)
    : 0

  // Threat ring
  const circumference = 2 * Math.PI * 52 // r=52
  const offset = circumference - (composite / 100) * circumference
  const ringFill = document.getElementById('ring-fill')
  ringFill.style.strokeDashoffset = offset
  ringFill.style.stroke = scoreColor(composite)

  document.getElementById('threat-value').textContent = composite

  const level = threatLevel(composite)
  const levelEl = document.getElementById('threat-level')
  levelEl.textContent = level.text
  levelEl.className = 'threat-level ' + level.css
  document.getElementById('threat-desc').textContent = threatDesc(level.text)

  // APO-DEX frame glow color
  const frame = document.getElementById('apodex-frame')
  const glowColor = scoreColor(composite)
  frame.style.borderColor = `${glowColor}22`
  frame.style.boxShadow = `0 0 60px ${glowColor}12, 0 4px 40px rgba(0,0,0,0.4), inset 0 1px 0 rgba(255,255,255,0.03)`

  // Calamity readouts
  const grid = document.getElementById('readout-grid')
  grid.innerHTML = Object.entries(CALAMITIES).map(([key, cal]) => {
    const risk = city.risks[key] || { score: 0, detail: 'No data available' }
    const isActive = active.includes(key)
    const color = scoreColor(risk.score)

    return `
      <div class="readout-card ${isActive ? '' : 'hidden'}">
        <div class="readout-top">
          <div class="readout-type">
            <div class="readout-icon ${key}">${cal.icon}</div>
            <span class="readout-name">${cal.name}</span>
          </div>
          <div class="readout-score" style="color: ${color}">${risk.score}</div>
        </div>
        <div class="readout-bar">
          <div class="readout-bar-fill" style="width: ${risk.score}%; background: ${color};"></div>
        </div>
        <div class="readout-detail">${risk.detail}</div>
      </div>
    `
  }).join('')

  // Nearest threats (from real volcano data if available)
  const nearbyContainer = document.getElementById('nearest-threats')
  const nearby = getNearbyVolcanoes(city.lat, city.lon)
  if (nearby.length > 0) {
    nearbyContainer.innerHTML = nearby.slice(0, 4).map(v => `
      <div class="threat-item">
        <span class="threat-item-icon">🌋</span>
        <span class="threat-item-name">${v.volcano_name}</span>
        <span class="threat-item-dist">${v.distance} km · Risk: ${Math.round(v.composite_risk_score || 0)}</span>
      </div>
    `).join('')
  } else {
    nearbyContainer.innerHTML = `
      <div class="threat-item">
        <span class="threat-item-icon">✓</span>
        <span style="color:#5a6270">No major volcanic threats within 300km</span>
      </div>
    `
  }

  // Mitigation
  const mitigationContainer = document.getElementById('mitigation-info')
  mitigationContainer.innerHTML = city.mitigation.map(m => `
    <div class="mitigation-item">
      <span class="mitigation-bullet">›</span>
      <span>${m}</span>
    </div>
  `).join('')

  // Update mini globe
  if (miniGlobe) {
    miniGlobe.setCity(city.lat, city.lon)
  }
}

// ============================================================
// EVENT HANDLERS
// ============================================================
citySelect.addEventListener('change', () => {
  currentCityIndex = parseInt(citySelect.value)
  renderApoDex()
})

document.querySelectorAll('.filter-item input').forEach(el => {
  el.addEventListener('change', () => {
    saveFiltersToStorage()
    renderApoDex()
  })
})

// ============================================================
// MINI GLOBE (Three.js shader earth)
// ============================================================
let miniGlobe = null

function initMiniGlobe() {
  const canvas = document.getElementById('mini-globe-canvas')
  if (!canvas) return

  const miniScene = new THREE.Scene()
  const miniCamera = new THREE.PerspectiveCamera(30, 1, 0.1, 100)
  miniCamera.position.z = 5.5

  const miniRenderer = new THREE.WebGLRenderer({
    canvas,
    antialias: true,
    alpha: true,
  })
  miniRenderer.setSize(180, 180)
  miniRenderer.setPixelRatio(Math.min(window.devicePixelRatio, 2))
  miniRenderer.setClearColor(0x000000, 0)

  const textureLoader = new THREE.TextureLoader()

  const dayTex = textureLoader.load('/earth/day.jpg')
  dayTex.colorSpace = THREE.SRGBColorSpace
  dayTex.anisotropy = 4

  const nightTex = textureLoader.load('/earth/night.jpg')
  nightTex.colorSpace = THREE.SRGBColorSpace
  nightTex.anisotropy = 4

  const specTex = textureLoader.load('/earth/specularClouds.jpg')
  specTex.anisotropy = 4

  const geo = new THREE.SphereGeometry(2, 48, 48)

  const earthMat = new THREE.ShaderMaterial({
    vertexShader: earthVertexShader,
    fragmentShader: earthFragmentShader,
    uniforms: {
      uDayTexture: new THREE.Uniform(dayTex),
      uNightTexture: new THREE.Uniform(nightTex),
      uSpecularCloudsTexture: new THREE.Uniform(specTex),
      uSunDirection: new THREE.Uniform(new THREE.Vector3(0, 0, 1)),
      uAtmosphereDayColor: new THREE.Uniform(new THREE.Color('#00aaff')),
      uAtmosphereTwilightColor: new THREE.Uniform(new THREE.Color('#ff6600')),
    },
  })

  const miniEarth = new THREE.Mesh(geo, earthMat)
  miniScene.add(miniEarth)

  const atmosMat = new THREE.ShaderMaterial({
    side: THREE.BackSide,
    transparent: true,
    vertexShader: atmosphereVertexShader,
    fragmentShader: atmosphereFragmentShader,
    uniforms: {
      uSunDirection: new THREE.Uniform(new THREE.Vector3(0, 0, 1)),
      uAtmosphereDayColor: new THREE.Uniform(new THREE.Color('#00aaff')),
      uAtmosphereTwilightColor: new THREE.Uniform(new THREE.Color('#ff6600')),
    },
  })

  const miniAtmos = new THREE.Mesh(geo, atmosMat)
  miniAtmos.scale.set(1.04, 1.04, 1.04)
  miniScene.add(miniAtmos)

  // Sun
  const sunDir = new THREE.Vector3()
  const sunSph = new THREE.Spherical(1, Math.PI * 0.5, 0.5)
  sunDir.setFromSpherical(sunSph)
  earthMat.uniforms.uSunDirection.value.copy(sunDir)
  atmosMat.uniforms.uSunDirection.value.copy(sunDir)

  let targetRotY = 0
  let currentRotY = 0

  function setCity(lat, lon) {
    // Rotate globe so the city's longitude faces the camera
    // offset by PI so the city is centered on screen
    targetRotY = -lon * Math.PI / 180 + Math.PI
  }

  const clock = new THREE.Clock()

  function tick() {
    const elapsed = clock.getElapsedTime()

    // Smoothly lerp toward target, plus slow auto-rotation
    currentRotY += (targetRotY - currentRotY) * 0.04
    miniEarth.rotation.y = currentRotY + elapsed * 0.03

    miniRenderer.render(miniScene, miniCamera)
    requestAnimationFrame(tick)
  }

  tick()

  return { setCity }
}

// ============================================================
// INIT
// ============================================================
async function init() {
  await loadVolcanoData()
  restoreFiltersFromStorage()
  miniGlobe = initMiniGlobe()
  renderApoDex()
}

init()
