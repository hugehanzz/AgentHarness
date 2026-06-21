<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import { useRoute } from 'vue-router'
import { ArrowUp, Refresh } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import claudeIcon from '../assets/agent-icons/claudecode-color.png'
import codexIcon from '../assets/agent-icons/codex-color.png'
import geminiIcon from '../assets/agent-icons/gemini-color.png'
import { api } from '../api/client'
import type { GeminiTaskBrief, GeminiTaskFacts } from '../api/types'

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
  startX: number
  startY: number
  moved: boolean
}

type BriefCacheEntry = {
  taskId: number
  factsVersion: string
  brief: GeminiTaskBrief
}

const storageKey = 'agentharness.floatingAgentPositions.v3'
const iconSize = 64
const iconGap = 10
const safeDistance = iconSize + iconGap
const viewportPadding = 14
const clickMoveTolerance = 4
const route = useRoute()

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
  startX: 0,
  startY: 0,
  moved: false,
})

const draggingClass = computed(() => dragState.key)
const suppressNextClick = ref(false)
const briefDialogVisible = ref(false)
const briefLoading = ref(false)
const briefError = ref('')
const brief = ref<GeminiTaskBrief | null>(null)
const chatDraft = ref('')
const briefCache = ref<BriefCacheEntry | null>(null)

const currentTaskId = computed(() => {
  const id = Number(route.params.id)
  return Number.isFinite(id) && id > 0 ? id : null
})

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
  dragState.startX = event.clientX
  dragState.startY = event.clientY
  dragState.moved = false
}

function onPointerMove(event: PointerEvent) {
  if (!dragState.key || dragState.pointerId !== event.pointerId) return
  if (
    Math.abs(event.clientX - dragState.startX) > clickMoveTolerance
    || Math.abs(event.clientY - dragState.startY) > clickMoveTolerance
  ) {
    dragState.moved = true
  }

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
  if (dragState.moved) {
    suppressNextClick.value = true
    window.setTimeout(() => {
      suppressNextClick.value = false
    }, 0)
  }
  savePositions()
  dragState.key = null
  dragState.pointerId = null
}

async function fetchGeminiBrief(taskId: number, factsVersion: string) {
  const { data } = await api.post<GeminiTaskBrief>(`/gemini/tasks/${taskId}/brief`)
  brief.value = data
  briefCache.value = {
    taskId,
    factsVersion: data.facts_version || factsVersion,
    brief: data,
  }
}

async function openGeminiBrief(forceRefresh = false) {
  if (!currentTaskId.value) {
    ElMessage.info('请先进入一个任务详情页，再打开 Gemini 简报')
    return
  }

  briefDialogVisible.value = true
  briefLoading.value = true
  briefError.value = ''
  if (forceRefresh) {
    brief.value = null
  }
  try {
    const taskId = currentTaskId.value
    const { data: facts } = await api.get<GeminiTaskFacts>(`/gemini/tasks/${taskId}/facts`)
    if (
      !forceRefresh
      && briefCache.value
      && briefCache.value.taskId === taskId
      && briefCache.value.factsVersion === facts.facts_version
    ) {
      brief.value = briefCache.value.brief
      return
    }
    await fetchGeminiBrief(taskId, facts.facts_version)
  } catch (error: any) {
    briefError.value = error?.response?.data?.detail || error?.message || 'Gemini brief request failed'
  } finally {
    briefLoading.value = false
  }
}

function refreshGeminiBrief() {
  openGeminiBrief(true)
}

function onAgentClick(key: AgentKey) {
  if (suppressNextClick.value) return
  if (key === 'gemini') {
    openGeminiBrief()
  }
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
      @click="onAgentClick(agent.key)"
    >
      <span class="agent-symbol" aria-hidden="true">
        <img class="brand-image" :src="agent.icon" :alt="agent.name" draggable="false">
      </span>
      <span class="sr-only">{{ agent.name }}</span>
    </button>

    <el-dialog
      v-model="briefDialogVisible"
      width="520px"
      class="gemini-chat-dialog"
      append-to-body
      :modal="false"
      :close-on-click-modal="false"
      :close-on-press-escape="false"
      :show-close="false"
      draggable
    >
      <template #header>
        <div class="chat-dialog-title">
          <div class="chat-title-identity">
            <span class="chat-title-avatar">
              <img :src="geminiIcon" alt="Gemini">
            </span>
            <div>
              <div class="chat-title-name">Gemini</div>
              <div class="chat-title-subtitle">{{ brief?.model || 'Secretary' }}</div>
            </div>
          </div>
          <div class="chat-title-actions">
            <el-button
              class="chat-icon-button"
              :icon="Refresh"
              :loading="briefLoading"
              circle
              @click="refreshGeminiBrief"
            />
            <el-button
              class="chat-icon-button"
              circle
              @click="briefDialogVisible = false"
            >
              <span class="chat-close-symbol" aria-hidden="true"></span>
            </el-button>
          </div>
        </div>
      </template>

      <div class="chat-shell">
        <div class="chat-window">
          <div v-if="briefLoading" class="chat-loading">
            <el-skeleton :rows="5" animated />
          </div>
          <el-alert
            v-else-if="briefError"
            :title="briefError"
            type="error"
            show-icon
            :closable="false"
          />
          <div v-else-if="brief" class="message-row is-gemini">
            <div class="message-avatar">
              <img :src="geminiIcon" alt="Gemini">
            </div>
            <div class="message-bubble">
              <section class="message-section">
                <div class="message-label">Summary</div>
                <p>{{ brief.summary }}</p>
              </section>
              <section class="message-section">
                <div class="message-label">Position</div>
                <p>{{ brief.current_position }}</p>
              </section>
              <section v-if="brief.pending_gate" class="message-section gate-section">
                <div class="message-label">Pending Gate</div>
                <div class="gate-card">
                  <strong>{{ brief.pending_gate.type }}</strong>
                  <span>{{ brief.pending_gate.owner }}</span>
                  <p>{{ brief.pending_gate.reason }}</p>
                </div>
              </section>
              <section v-if="brief.suggested_next_steps.length" class="message-section">
                <div class="message-label">Next Steps</div>
                <ul>
                  <li v-for="step in brief.suggested_next_steps" :key="step">{{ step }}</li>
                </ul>
              </section>
              <section v-if="brief.risk_notes.length" class="message-section">
                <div class="message-label">Risk Notes</div>
                <ul>
                  <li v-for="note in brief.risk_notes" :key="note">{{ note }}</li>
                </ul>
              </section>
            </div>
          </div>
        </div>

        <div class="chat-composer">
          <div class="composer-box">
            <el-input
              v-model="chatDraft"
              class="composer-input"
              type="textarea"
              :rows="3"
              resize="none"
              disabled
              placeholder="对话输入稍后接入"
            />
            <el-button
              class="composer-send-button"
              :icon="ArrowUp"
              circle
              disabled
            />
          </div>
        </div>
      </div>
    </el-dialog>
  </div>
</template>

<style scoped>
.floating-agent-layer {
  position: fixed;
  inset: 0;
  z-index: 80;
  pointer-events: none;
}

:global(.el-dialog.gemini-chat-dialog.is-draggable .el-dialog__header),
:global(.el-dialog.gemini-chat-dialog.is-draggable .el-dialog__header *) {
  cursor: default !important;
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

.chat-dialog-title {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.chat-title-identity {
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
}

.chat-title-avatar,
.message-avatar {
  display: grid;
  place-items: center;
  width: 38px;
  height: 38px;
  border: 1px solid rgba(16, 24, 40, 0.1);
  border-radius: 50%;
  background: rgba(255, 255, 255, 0.78);
  box-shadow: 0 6px 14px rgba(16, 24, 40, 0.12);
}

.chat-title-avatar img,
.message-avatar img {
  width: 25px;
  height: 25px;
  object-fit: contain;
}

.chat-title-name {
  font-size: 14px;
  font-weight: 800;
  color: #182235;
  line-height: 1.2;
}

.chat-title-subtitle {
  margin-top: 2px;
  font-size: 12px;
  color: #75839a;
}

.chat-title-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex: 0 0 auto;
}

.chat-icon-button {
  flex: 0 0 auto;
  width: 32px;
  height: 32px;
  border-color: rgba(16, 24, 40, 0.12);
  background: rgba(255, 255, 255, 0.74);
  color: #64748b;
  font-size: 14px;
}

.chat-icon-button:hover,
.chat-icon-button:focus-visible {
  border-color: rgba(7, 133, 141, 0.28);
  background: rgba(240, 253, 250, 0.82);
  color: #0f766e;
}

.chat-icon-button + .chat-icon-button {
  margin-left: 0;
}

.chat-close-symbol {
  position: relative;
  display: block;
  width: 14px;
  height: 14px;
}

.chat-close-symbol::before,
.chat-close-symbol::after {
  position: absolute;
  top: 50%;
  left: 50%;
  width: 12px;
  height: 1.4px;
  border-radius: 999px;
  background: currentColor;
  content: "";
  transform-origin: center;
}

.chat-close-symbol::before {
  transform: translate(-50%, -50%) rotate(45deg);
}

.chat-close-symbol::after {
  transform: translate(-50%, -50%) rotate(-45deg);
}

.chat-shell {
  display: grid;
  grid-template-rows: minmax(260px, 46vh) auto;
  overflow: hidden;
  border: 1px solid rgba(16, 24, 40, 0.08);
  border-radius: 8px;
  background: #f7f8fa;
}

.chat-window {
  min-height: 0;
  padding: 18px 16px;
  overflow-y: auto;
}

.chat-loading {
  padding: 4px 2px;
}

.message-row {
  display: flex;
  align-items: flex-start;
  gap: 10px;
}

.message-avatar {
  flex: 0 0 auto;
  width: 36px;
  height: 36px;
  background: rgba(255, 255, 255, 0.86);
}

.message-avatar img {
  width: 24px;
  height: 24px;
}

.message-bubble {
  display: grid;
  max-width: min(390px, calc(100% - 50px));
  gap: 12px;
  padding: 12px 14px;
  border: 1px solid rgba(16, 24, 40, 0.06);
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.94);
  box-shadow: 0 8px 18px rgba(16, 24, 40, 0.08);
}

.message-section {
  display: grid;
  gap: 5px;
}

.message-section p {
  margin: 0;
  color: #26364d;
  line-height: 1.65;
}

.message-section ul {
  display: grid;
  gap: 7px;
  margin: 0;
  padding-left: 18px;
  color: #26364d;
  line-height: 1.55;
}

.message-label {
  font-size: 11px;
  font-weight: 800;
  color: #64748b;
  text-transform: uppercase;
}

.gate-card {
  display: grid;
  gap: 4px;
  padding: 10px 12px;
  border: 1px solid rgba(245, 158, 11, 0.24);
  border-radius: 8px;
  background: rgba(255, 251, 235, 0.82);
  color: #3b2f12;
}

.gate-card span {
  font-size: 12px;
  color: #936316;
}

.chat-composer {
  padding: 12px;
  border-top: 1px solid rgba(16, 24, 40, 0.08);
  background: rgba(255, 255, 255, 0.88);
}

.composer-box {
  position: relative;
  min-height: 118px;
  padding: 14px 54px 14px 16px;
  border: 1px solid rgba(16, 24, 40, 0.12);
  border-radius: 26px;
  background: rgba(255, 255, 255, 0.95);
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.9);
}

.composer-input {
  height: 100%;
}

.composer-input :deep(.el-textarea__inner) {
  min-height: 86px !important;
  padding: 0;
  border: 0;
  box-shadow: none;
  background: transparent;
  color: #26364d;
  line-height: 1.55;
  resize: none;
}

.composer-input :deep(.el-textarea__inner::placeholder) {
  color: #a8b2c2;
}

.composer-input.is-disabled :deep(.el-textarea__inner) {
  background: transparent;
  box-shadow: none;
  color: #8a96a8;
  -webkit-text-fill-color: #8a96a8;
}

.composer-send-button {
  position: absolute;
  right: 14px;
  bottom: 14px;
  width: 36px;
  height: 36px;
  border: 0;
  background: #8c939d;
  color: #ffffff;
}

.composer-send-button.is-disabled,
.composer-send-button.is-disabled:hover,
.composer-send-button.is-disabled:focus {
  background: #8c939d;
  color: #ffffff;
  opacity: 0.8;
}

</style>
