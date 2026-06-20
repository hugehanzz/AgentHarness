<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive } from 'vue'
import claudeIcon from '../assets/agent-icons/claudecode-color.png'
import codexIcon from '../assets/agent-icons/codex-color.png'
import geminiIcon from '../assets/agent-icons/gemini-color.png'

type AgentKey = 'codex' | 'claude' | 'gemini'

type AgentIcon = {
  key: AgentKey
  name: string
  icon: string
}

type Position = {
  x: number
  y: number
}

type DragState = {
  key: AgentKey | null
  pointerId: number | null
  offsetX: number
  offsetY: number
}

const storageKey = 'agentharness.floatingAgentPositions.v3'
const iconSize = 64
const iconGap = 10
const safeDistance = iconSize + iconGap
const viewportPadding = 14

const agents: AgentIcon[] = [
  { key: 'codex', name: 'Codex', icon: codexIcon },
  { key: 'claude', name: 'Claude', icon: claudeIcon },
  { key: 'gemini', name: 'Gemini', icon: geminiIcon },
]

const positions = reactive<Record<AgentKey, Position>>({
  codex: { x: 0, y: 0 },
  claude: { x: 0, y: 0 },
  gemini: { x: 0, y: 0 },
})

const dragState = reactive<DragState>({
  key: null,
  pointerId: null,
  offsetX: 0,
  offsetY: 0,
})

const draggingClass = computed(() => dragState.key)

function defaultPositions() {
  const right = Math.max(viewportPadding, window.innerWidth - iconSize - 26)
  const centerY = Math.max(96, Math.round(window.innerHeight / 2 - ((agents.length * iconSize + (agents.length - 1) * iconGap) / 2)))

  return {
    codex: { x: right, y: centerY },
    claude: { x: right, y: centerY + safeDistance },
    gemini: { x: right, y: centerY + safeDistance * 2 },
  }
}

function clampPosition(position: Position): Position {
  const maxX = Math.max(viewportPadding, window.innerWidth - iconSize - viewportPadding)
  const maxY = Math.max(viewportPadding, window.innerHeight - iconSize - viewportPadding)

  return {
    x: Math.min(Math.max(position.x, viewportPadding), maxX),
    y: Math.min(Math.max(position.y, viewportPadding), maxY),
  }
}

function hasOverlap(key: AgentKey, candidate: Position) {
  return agents.some((agent) => {
    if (agent.key === key) return false
    const other = positions[agent.key]
    return (
      Math.abs(candidate.x - other.x) < iconSize + iconGap
      && Math.abs(candidate.y - other.y) < iconSize + iconGap
    )
  })
}

function isOverlapping(source: Position, target: Position) {
  return Math.abs(source.x - target.x) < safeDistance && Math.abs(source.y - target.y) < safeDistance
}

function directionFor(value: number, sourceKey: AgentKey, targetKey: AgentKey) {
  if (value !== 0) return value > 0 ? 1 : -1
  const sourceIndex = agents.findIndex((agent) => agent.key === sourceKey)
  const targetIndex = agents.findIndex((agent) => agent.key === targetKey)
  return targetIndex > sourceIndex ? 1 : -1
}

function overlapAmount(source: Position, target: Position) {
  return {
    x: safeDistance - Math.abs(target.x - source.x),
    y: safeDistance - Math.abs(target.y - source.y),
  }
}

function pushCandidate(sourceKey: AgentKey, targetKey: AgentKey, axis: 'x' | 'y') {
  const source = positions[sourceKey]
  const target = positions[targetKey]
  const overlap = overlapAmount(source, target)
  const next = { ...target }

  if (axis === 'x') {
    next.x += overlap.x * directionFor(target.x - source.x, sourceKey, targetKey)
  } else {
    next.y += overlap.y * directionFor(target.y - source.y, sourceKey, targetKey)
  }

  return clampPosition(next)
}

function pushAway(sourceKey: AgentKey, targetKey: AgentKey) {
  const source = positions[sourceKey]
  const target = positions[targetKey]
  if (!isOverlapping(source, target)) return false

  const overlap = overlapAmount(source, target)
  const firstAxis = overlap.x <= overlap.y ? 'x' : 'y'
  const secondAxis = firstAxis === 'x' ? 'y' : 'x'
  const firstCandidate = pushCandidate(sourceKey, targetKey, firstAxis)
  const secondCandidate = pushCandidate(sourceKey, targetKey, secondAxis)
  const firstStillOverlaps = isOverlapping(source, firstCandidate)
  const secondStillOverlaps = isOverlapping(source, secondCandidate)
  const next = !firstStillOverlaps || secondStillOverlaps ? firstCandidate : secondCandidate

  positions[targetKey].x = next.x
  positions[targetKey].y = next.y
  return true
}

function resolvePushAway(activeKey: AgentKey) {
  for (let pass = 0; pass < agents.length; pass += 1) {
    agents.forEach((sourceAgent) => {
      agents.forEach((targetAgent) => {
        if (sourceAgent.key === targetAgent.key) return
        if (targetAgent.key === activeKey) return
        pushAway(sourceAgent.key, targetAgent.key)
      })
    })
  }
}

function applyPositions(nextPositions: Record<AgentKey, Position>) {
  const fallback = defaultPositions()
  agents.forEach((agent) => {
    const clamped = clampPosition(nextPositions[agent.key] || fallback[agent.key])
    positions[agent.key].x = clamped.x
    positions[agent.key].y = clamped.y
  })

  agents.forEach((agent) => {
    if (hasOverlap(agent.key, positions[agent.key])) {
      const clamped = clampPosition(fallback[agent.key])
      positions[agent.key].x = clamped.x
      positions[agent.key].y = clamped.y
    }
  })

  agents.forEach((agent) => resolvePushAway(agent.key))
}

function loadPositions() {
  const fallback = defaultPositions()
  const saved = window.localStorage.getItem(storageKey)
  if (!saved) {
    applyPositions(fallback)
    return
  }

  try {
    const parsed = JSON.parse(saved) as Partial<Record<AgentKey, Position>>
    applyPositions({
      codex: parsed.codex || fallback.codex,
      claude: parsed.claude || fallback.claude,
      gemini: parsed.gemini || fallback.gemini,
    })
  } catch {
    applyPositions(fallback)
  }
}

function savePositions() {
  window.localStorage.setItem(storageKey, JSON.stringify(positions))
}

function onPointerDown(event: PointerEvent, key: AgentKey) {
  const target = event.currentTarget as HTMLElement
  target.setPointerCapture(event.pointerId)
  dragState.key = key
  dragState.pointerId = event.pointerId
  dragState.offsetX = event.clientX - positions[key].x
  dragState.offsetY = event.clientY - positions[key].y
}

function onPointerMove(event: PointerEvent) {
  if (!dragState.key || dragState.pointerId !== event.pointerId) return

  const clamped = clampPosition({
    x: event.clientX - dragState.offsetX,
    y: event.clientY - dragState.offsetY,
  })
  const current = positions[dragState.key]
  current.x = clamped.x
  current.y = clamped.y
  resolvePushAway(dragState.key)
}

function onPointerUp(event: PointerEvent) {
  if (!dragState.key || dragState.pointerId !== event.pointerId) return
  savePositions()
  dragState.key = null
  dragState.pointerId = null
}

function onViewportResize() {
  applyPositions(positions)
  savePositions()
}

onMounted(() => {
  loadPositions()
  window.addEventListener('resize', onViewportResize)
})

onBeforeUnmount(() => {
  window.removeEventListener('resize', onViewportResize)
})
</script>

<template>
  <div class="floating-agent-layer" aria-label="Floating agent shortcuts">
    <button
      v-for="agent in agents"
      :key="agent.key"
      :class="['floating-agent-icon', { 'is-dragging': draggingClass === agent.key }]"
      :style="{ transform: `translate3d(${positions[agent.key].x}px, ${positions[agent.key].y}px, 0)` }"
      :title="agent.name"
      type="button"
      @pointermove="onPointerMove"
      @pointerdown="onPointerDown($event, agent.key)"
      @pointerup="onPointerUp"
      @pointercancel="onPointerUp"
    >
      <span class="agent-symbol" aria-hidden="true">
        <img class="brand-image" :src="agent.icon" :alt="agent.name" draggable="false">
      </span>
      <span class="sr-only">{{ agent.name }}</span>
    </button>
  </div>
</template>

<style scoped>
.floating-agent-layer {
  position: fixed;
  inset: 0;
  z-index: 80;
  pointer-events: none;
}

.floating-agent-icon {
  position: absolute;
  top: 0;
  left: 0;
  display: grid;
  place-items: center;
  width: 64px;
  height: 64px;
  padding: 9px;
  border: 1px solid rgba(16, 24, 40, 0.12);
  border-radius: 50%;
  background: rgba(255, 255, 255, 1.0);
  backdrop-filter: blur(10px);
  box-shadow: 0 14px 28px rgba(16, 24, 40, 0.16), inset 0 1px 0 rgba(255, 255, 255, 0.9);
  color: #102a43;
  cursor: grab;
  pointer-events: auto;
  touch-action: none;
  user-select: none;
  transition: transform 120ms ease, box-shadow 140ms ease, border-color 140ms ease;
}

.floating-agent-icon:hover,
.floating-agent-icon:focus-visible {
  border-color: rgba(7, 133, 141, 0.36);
  box-shadow: 0 16px 30px rgba(16, 24, 40, 0.18), 0 0 0 2px rgba(7, 133, 141, 0.08);
  outline: none;
}

.floating-agent-icon.is-dragging {
  cursor: grabbing;
  box-shadow: 0 16px 30px rgba(16, 24, 40, 0.18), 0 0 0 2px rgba(7, 133, 141, 0.08);
  transition: box-shadow 140ms ease, border-color 140ms ease;
}

.agent-symbol {
  position: relative;
  display: grid;
  place-items: center;
  width: 100%;
  height: 100%;
}

.brand-image {
  display: block;
  width: 100%;
  height: 100%;
  object-fit: contain;
  pointer-events: none;
}

.sr-only {
  position: absolute;
  width: 1px;
  height: 1px;
  padding: 0;
  margin: -1px;
  overflow: hidden;
  clip: rect(0, 0, 0, 0);
  white-space: nowrap;
  border: 0;
}

</style>
