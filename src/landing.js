import * as THREE from 'three'
import gsap from 'gsap'
import { ScrollTrigger } from 'gsap/ScrollTrigger'

import earthVertexShader from './shaders/earth/vertex.glsl'
import earthFragmentShader from './shaders/earth/fragment.glsl'
import atmosphereVertexShader from './shaders/atmosphere/vertex.glsl'
import atmosphereFragmentShader from './shaders/atmosphere/fragment.glsl'

gsap.registerPlugin(ScrollTrigger)

// ============================================================
// SETUP
// ============================================================
const canvas = document.querySelector('canvas.webgl')
const scene = new THREE.Scene()
const textureLoader = new THREE.TextureLoader()

const sizes = {
  width: window.innerWidth,
  height: window.innerHeight,
  pixelRatio: Math.min(window.devicePixelRatio, 2),
}

// ============================================================
// EARTH TEXTURES
// ============================================================
const earthDayTexture = textureLoader.load('/earth/day.jpg')
earthDayTexture.colorSpace = THREE.SRGBColorSpace
earthDayTexture.anisotropy = 8

const earthNightTexture = textureLoader.load('/earth/night.jpg')
earthNightTexture.colorSpace = THREE.SRGBColorSpace
earthNightTexture.anisotropy = 8

const earthSpecularCloudsTexture = textureLoader.load('/earth/specularClouds.jpg')
earthSpecularCloudsTexture.anisotropy = 8

// ============================================================
// EARTH MESH + ATMOSPHERE (from old earth code shaders)
// ============================================================
const earthGroup = new THREE.Group()
scene.add(earthGroup)

const earthGeometry = new THREE.SphereGeometry(2, 64, 64)

const earthMaterial = new THREE.ShaderMaterial({
  vertexShader: earthVertexShader,
  fragmentShader: earthFragmentShader,
  uniforms: {
    uDayTexture: new THREE.Uniform(earthDayTexture),
    uNightTexture: new THREE.Uniform(earthNightTexture),
    uSpecularCloudsTexture: new THREE.Uniform(earthSpecularCloudsTexture),
    uSunDirection: new THREE.Uniform(new THREE.Vector3(0, 0, 1)),
    uAtmosphereDayColor: new THREE.Uniform(new THREE.Color('#00aaff')),
    uAtmosphereTwilightColor: new THREE.Uniform(new THREE.Color('#ff6600')),
  },
})

const earth = new THREE.Mesh(earthGeometry, earthMaterial)
earthGroup.add(earth)

// Atmosphere (slightly larger, renders on back face for glow effect)
const atmosphereMaterial = new THREE.ShaderMaterial({
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

const atmosphere = new THREE.Mesh(earthGeometry, atmosphereMaterial)
atmosphere.scale.set(1.04, 1.04, 1.04)
earthGroup.add(atmosphere)

// ============================================================
// STAR PARTICLES (background depth)
// ============================================================
const starsCount = 800
const starsPositions = new Float32Array(starsCount * 3)
const starsSizes = new Float32Array(starsCount)

for (let i = 0; i < starsCount; i++) {
  // Distribute stars in a sphere around the scene
  const radius = 15 + Math.random() * 35
  const theta = Math.random() * Math.PI * 2
  const phi = Math.acos(2 * Math.random() - 1)
  starsPositions[i * 3] = radius * Math.sin(phi) * Math.cos(theta)
  starsPositions[i * 3 + 1] = radius * Math.sin(phi) * Math.sin(theta)
  starsPositions[i * 3 + 2] = radius * Math.cos(phi)
  starsSizes[i] = Math.random()
}

const starsGeometry = new THREE.BufferGeometry()
starsGeometry.setAttribute('position', new THREE.BufferAttribute(starsPositions, 3))

const starsMaterial = new THREE.PointsMaterial({
  size: 0.06,
  sizeAttenuation: true,
  color: '#ffffff',
  transparent: true,
  opacity: 0.6,
})

const stars = new THREE.Points(starsGeometry, starsMaterial)
scene.add(stars)

// ============================================================
// SUN DIRECTION (drives day/night + atmosphere shader)
// ============================================================
const sunSpherical = new THREE.Spherical(1, Math.PI * 0.5, 0.5)
const sunDirection = new THREE.Vector3()

function updateSun() {
  sunDirection.setFromSpherical(sunSpherical)
  earthMaterial.uniforms.uSunDirection.value.copy(sunDirection)
  atmosphereMaterial.uniforms.uSunDirection.value.copy(sunDirection)
}

updateSun()

// Atmosphere color targets for scroll transition
const atmosDayStart = new THREE.Color('#00aaff')
const atmosDayEnd = new THREE.Color('#8b0000')
const atmosTwilightStart = new THREE.Color('#ff6600')
const atmosTwilightEnd = new THREE.Color('#cc1100')
const atmosDayCurrent = new THREE.Color()
const atmosTwilightCurrent = new THREE.Color()

// ============================================================
// CAMERA (with parallax group)
// ============================================================
const cameraGroup = new THREE.Group()
scene.add(cameraGroup)

const camera = new THREE.PerspectiveCamera(
  40,
  sizes.width / sizes.height,
  0.1,
  100
)
camera.position.z = 7
cameraGroup.add(camera)

// ============================================================
// RENDERER
// ============================================================
const renderer = new THREE.WebGLRenderer({
  canvas,
  antialias: true,
})
renderer.setSize(sizes.width, sizes.height)
renderer.setPixelRatio(sizes.pixelRatio)
renderer.setClearColor('#07080c')

// ============================================================
// SCROLL STATE
// ============================================================
let scrollY = 0

window.addEventListener('scroll', () => {
  scrollY = window.scrollY
})

// ============================================================
// CONTENT SECTION REVEAL (Intersection Observer)
// ============================================================
const revealObserver = new IntersectionObserver(
  (entries) => {
    entries.forEach((entry) => {
      if (entry.isIntersecting) {
        entry.target.classList.add('visible')
      } else {
        // Remove class when out of view so it re-animates on scroll back
        entry.target.classList.remove('visible')
      }
    })
  },
  { threshold: 0.15 }
)

document.querySelectorAll('.section-inner').forEach((el) => {
  revealObserver.observe(el)
})

// ============================================================
// MOUSE PARALLAX
// ============================================================
const cursor = { x: 0, y: 0 }

window.addEventListener('mousemove', (e) => {
  cursor.x = e.clientX / sizes.width - 0.5
  cursor.y = e.clientY / sizes.height - 0.5
})

// ============================================================
// RESIZE
// ============================================================
window.addEventListener('resize', () => {
  sizes.width = window.innerWidth
  sizes.height = window.innerHeight
  sizes.pixelRatio = Math.min(window.devicePixelRatio, 2)

  camera.aspect = sizes.width / sizes.height
  camera.updateProjectionMatrix()

  renderer.setSize(sizes.width, sizes.height)
  renderer.setPixelRatio(sizes.pixelRatio)
})

// ============================================================
// ANIMATION LOOP
// ============================================================
const clock = new THREE.Clock()
let previousTime = 0

function tick() {
  const elapsedTime = clock.getElapsedTime()
  const deltaTime = elapsedTime - previousTime
  previousTime = elapsedTime

  // ---- Scroll progress (0 to 1 over the first viewport height) ----
  const p = Math.min(scrollY / sizes.height, 1)

  // Ease the progress for smoother visual (cubic ease-out)
  const ep = 1 - Math.pow(1 - p, 3)

  // ---- Earth: slow rotation ----
  earth.rotation.y = elapsedTime * 0.06

  // ---- Earth: scroll-driven push back + drift down ----
  earthGroup.position.z = -ep * 6
  earthGroup.position.y = -ep * 1.5

  // ---- Dawn effect: sun moves behind the earth ----
  // theta goes from 0.5 (front-lit) to ~PI (backlit = dawn rim)
  sunSpherical.theta = 0.5 + ep * 2.6
  updateSun()

  // ---- Scroll indicator: fade out as user scrolls ----
  const indicator = document.querySelector('.scroll-indicator')
  if (indicator) {
    if (scrollY > 10) {
      // Kill the CSS animation so inline opacity takes effect
      indicator.style.animation = 'none'
    }
    const fadeProgress = Math.min(scrollY / (sizes.height * 0.12), 1)
    indicator.style.opacity = String(1 - fadeProgress)
    indicator.style.transform = `translateX(-50%) translateY(${-fadeProgress * 30}px)`
    if (fadeProgress >= 1) {
      indicator.style.display = 'none'
    } else {
      indicator.style.display = ''
    }
  }

  // ---- Atmosphere: expand glow + shift to dark red with scroll ----
  const atmosScale = 1.04 + ep * 0.18  // 1.04 → 1.22
  atmosphere.scale.set(atmosScale, atmosScale, atmosScale)

  // Lerp atmosphere colors from cool blue/orange → dark apocalyptic red
  atmosDayCurrent.copy(atmosDayStart).lerp(atmosDayEnd, ep)
  atmosTwilightCurrent.copy(atmosTwilightStart).lerp(atmosTwilightEnd, ep)

  earthMaterial.uniforms.uAtmosphereDayColor.value.copy(atmosDayCurrent)
  earthMaterial.uniforms.uAtmosphereTwilightColor.value.copy(atmosTwilightCurrent)
  atmosphereMaterial.uniforms.uAtmosphereDayColor.value.copy(atmosDayCurrent)
  atmosphereMaterial.uniforms.uAtmosphereTwilightColor.value.copy(atmosTwilightCurrent)

  // ---- Hero tagline: fade as user scrolls ----
  const heroContent = document.querySelector('.hero-content')
  if (heroContent) {
    const heroFade = Math.min(scrollY / (sizes.height * 0.4), 1)
    heroContent.style.opacity = String(1 - heroFade)
    heroContent.style.transform = `translateY(${-heroFade * 60}px)`
  }

  // ---- Mouse parallax (smooth eased follow) ----
  const parallaxX = cursor.x * 0.4
  const parallaxY = -cursor.y * 0.4
  cameraGroup.position.x += (parallaxX - cameraGroup.position.x) * 3 * deltaTime
  cameraGroup.position.y += (parallaxY - cameraGroup.position.y) * 3 * deltaTime

  // ---- Stars: subtle rotation for depth ----
  stars.rotation.y = elapsedTime * 0.008
  stars.rotation.x = elapsedTime * 0.003

  // ---- Render ----
  renderer.render(scene, camera)
  requestAnimationFrame(tick)
}

tick()
