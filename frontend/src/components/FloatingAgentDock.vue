<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { ArrowUp, Refresh } from '@element-plus/icons-vue'
import claudeIcon from '../assets/agent-icons/claudecode-color.png'
import codexIcon from '../assets/agent-icons/codex-color.png'
import geminiIcon from '../assets/agent-icons/gemini-color.png'
import { api } from '../api/client'
import type { GeminiTaskBrief, GeminiTaskFacts } from '../api/types'
import { useTasksStore } from '../stores/tasks'

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

type HomeGeminiMessage = {
  text: string
}

type ChatMessage = {
  id: number
  role: 'user' | 'assistant'
  text: string
  status?: 'streaming' | 'done' | 'failed'
}

type GeminiChatHistoryItem = {
  role: 'user' | 'assistant'
  content: string
}

type SsePayload = {
  event: string
  data: Record<string, any>
}

const storageKey = 'agentharness.floatingAgentPositions.v3'
const iconSize = 64
const iconGap = 10
const safeDistance = iconSize + iconGap
const viewportPadding = 14
const clickMoveTolerance = 4
const fallbackGeminiModel = 'gemini-3.1-flash-lite'
const renderDeltaDelayMs = 24
const route = useRoute()
const store = useTasksStore()

const agents: AgentIcon[] = [
  { key: 'codex', name: 'Codex', icon: codexIcon },
  { key: 'claude', name: 'Claude', icon: claudeIcon },
  { key: 'gemini', name: 'Gemini', icon: geminiIcon },
]

const geminiBriefPrefetchStatuses = new Set([
  'PLAN_READY',
  'IMPLEMENT_DONE',
  'REVIEW_DONE',
  'RECHECK_DONE',
  'ACCEPTANCE_READY',
  'ACCEPTANCE_PASSED',
  'ARCHIVED',
  'DONE',
])

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
const briefPrefetching = ref(false)
const homeGeminiMessage = ref<HomeGeminiMessage | null>(null)
const chatMessagesByScope = reactive<Record<string, ChatMessage[]>>({})
const chatWindowRef = ref<HTMLElement | null>(null)
const chatStreaming = ref(false)
let nextChatMessageId = 1

const currentTaskId = computed(() => {
  const id = Number(route.params.id)
  return Number.isFinite(id) && id > 0 ? id : null
})

const geminiModelLabel = computed(() => brief.value?.model || fallbackGeminiModel)
const canSendChatDraft = computed(() => chatDraft.value.trim().length > 0 && !chatStreaming.value)
const activeChatScope = computed(() => (currentTaskId.value ? `task:${currentTaskId.value}` : 'home'))
const activeChatMessages = computed(() => chatMessagesByScope[activeChatScope.value] || [])

const taskFactsTrigger = computed(() => {
  if (!currentTaskId.value) return ''
  return [
    currentTaskId.value,
    store.selectedTask?.status || '',
    store.selectedTask?.updated_at || '',
    store.events.length,
  ].join(':')
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
  // Keep the three agent icons independently draggable while preventing overlap.
  // The dragged icon is authoritative; nearby icons are gently pushed away.
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

async function prefetchGeminiBrief() {
  if (!currentTaskId.value || briefPrefetching.value) return
  if (!store.selectedTask || !geminiBriefPrefetchStatuses.has(store.selectedTask.status)) return

  // Brief generation is slow enough to feel blank on click, so key workflow
  // states warm the cache in the background and rely on facts_version to expire.
  briefPrefetching.value = true
  try {
    const taskId = currentTaskId.value
    const { data: facts } = await api.get<GeminiTaskFacts>(`/gemini/tasks/${taskId}/facts`)
    if (
      briefCache.value
      && briefCache.value.taskId === taskId
      && briefCache.value.factsVersion === facts.facts_version
    ) {
      return
    }
    await fetchGeminiBrief(taskId, facts.facts_version)
  } catch {
    // Background prefetch is best effort; explicit open/refresh will surface errors.
  } finally {
    briefPrefetching.value = false
  }
}

async function openGeminiBrief(forceRefresh = false) {
  if (!currentTaskId.value) {
    briefDialogVisible.value = true
    briefLoading.value = false
    briefError.value = ''
    brief.value = null
    homeGeminiMessage.value = { text: '你好，我是Gemini~' }
    return
  }

  briefDialogVisible.value = true
  briefError.value = ''
  homeGeminiMessage.value = null
  const cachedBrief = briefCache.value?.taskId === currentTaskId.value ? briefCache.value.brief : null
  if (forceRefresh) {
    brief.value = null
  } else if (cachedBrief) {
    brief.value = cachedBrief
  } else {
    brief.value = null
  }
  briefLoading.value = forceRefresh || !brief.value
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
  if (!currentTaskId.value) {
    clearChatMessages('home')
  }
  openGeminiBrief(true)
}

function ensureChatMessages(scope = activeChatScope.value) {
  if (!chatMessagesByScope[scope]) {
    chatMessagesByScope[scope] = []
  }
  return chatMessagesByScope[scope]
}

function clearChatMessages(scope = activeChatScope.value) {
  chatMessagesByScope[scope] = []
}

function updateChatMessage(scope: string, id: number, updater: (message: ChatMessage) => ChatMessage) {
  const messages = chatMessagesByScope[scope]
  if (!messages) return
  const index = messages.findIndex((message) => message.id === id)
  if (index < 0) return
  // Replace the array item instead of mutating a captured object reference.
  // This makes every streamed Gemini delta reliably trigger Vue rendering.
  messages[index] = updater(messages[index])
}

function closeGeminiDialog() {
  if (!currentTaskId.value) {
    clearChatMessages('home')
  }
  briefDialogVisible.value = false
}

async function scrollChatToBottom() {
  await nextTick()
  if (!chatWindowRef.value) return
  chatWindowRef.value.scrollTop = chatWindowRef.value.scrollHeight
}

function delay(ms: number) {
  return new Promise((resolve) => {
    window.setTimeout(resolve, ms)
  })
}

function nextAnimationFrame() {
  return new Promise((resolve) => {
    window.requestAnimationFrame(resolve)
  })
}

async function flushChatRender() {
  await scrollChatToBottom()
  await nextAnimationFrame()
}

function buildChatHistory(messages: ChatMessage[]): GeminiChatHistoryItem[] {
  return messages
    .filter((message) => message.text.trim() && message.status !== 'streaming' && message.status !== 'failed')
    .slice(-8)
    .map((message) => ({
      role: message.role,
      content: message.text.trim(),
    }))
}

function parseSseBlock(block: string): SsePayload | null {
  const lines = block.split('\n')
  let event = 'message'
  const dataLines: string[] = []

  lines.forEach((line) => {
    if (line.startsWith('event:')) {
      event = line.slice(6).trim()
    } else if (line.startsWith('data:')) {
      dataLines.push(line.slice(5).trimStart())
    }
  })

  if (!dataLines.length) return null

  try {
    return {
      event,
      data: JSON.parse(dataLines.join('\n')),
    }
  } catch {
    return null
  }
}

function collectSseEvents(buffer: string): { events: SsePayload[]; remaining: string } {
  // A network read can contain partial, one, or many SSE frames. Keep the
  // unfinished tail in the buffer and emit only complete "\n\n" blocks.
  const normalized = buffer.replace(/\r\n/g, '\n')
  const blocks = normalized.split('\n\n')
  const remaining = blocks.pop() || ''
  const events = blocks
    .map((block) => parseSseBlock(block))
    .filter((event): event is SsePayload => Boolean(event))
  return { events, remaining }
}

async function streamGeminiReply(text: string, assistantMessageId: number, history: GeminiChatHistoryItem[], scope: string) {
  const taskId = currentTaskId.value
  const url = taskId ? `/api/gemini/tasks/${taskId}/chat/stream` : '/api/gemini/chat/stream'
  const response = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ message: text, history }),
  })

  if (!response.ok) {
    throw new Error(`Gemini chat request failed: ${response.status}`)
  }
  if (!response.body) {
    throw new Error('Gemini chat response did not include a stream')
  }

  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  // Read the browser stream directly instead of using axios; axios does not
  // expose incremental response body reads in the browser.
  while (true) {
    const { value, done } = await reader.read()
    if (done) break

    buffer += decoder.decode(value, { stream: true })
    const parsed = collectSseEvents(buffer)
    buffer = parsed.remaining

    for (const event of parsed.events) {
      if (event.event === 'delta') {
        updateChatMessage(scope, assistantMessageId, (message) => ({
          ...message,
          text: message.text + String(event.data.text || ''),
        }))
        await flushChatRender()
        await delay(renderDeltaDelayMs)
      } else if (event.event === 'error') {
        throw new Error(String(event.data.detail || 'Gemini chat request failed'))
      } else if (event.event === 'done') {
        updateChatMessage(scope, assistantMessageId, (message) => ({ ...message, status: 'done' }))
      }
    }
  }

  buffer += decoder.decode()
  const parsed = collectSseEvents(`${buffer}\n\n`)
  for (const event of parsed.events) {
    if (event.event === 'delta') {
      updateChatMessage(scope, assistantMessageId, (message) => ({
        ...message,
        text: message.text + String(event.data.text || ''),
      }))
      await flushChatRender()
      await delay(renderDeltaDelayMs)
    } else if (event.event === 'error') {
      throw new Error(String(event.data.detail || 'Gemini chat request failed'))
    } else if (event.event === 'done') {
      updateChatMessage(scope, assistantMessageId, (message) => ({ ...message, status: 'done' }))
    }
  }

  const assistantMessage = chatMessagesByScope[scope]?.find((message) => message.id === assistantMessageId)
  if (!assistantMessage?.text.trim()) {
    updateChatMessage(scope, assistantMessageId, (message) => ({
      ...message,
      text: 'Gemini 没有返回内容。',
    }))
  }
  updateChatMessage(scope, assistantMessageId, (message) => ({ ...message, status: 'done' }))
  await flushChatRender()
}

async function sendChatDraft() {
  const text = chatDraft.value.trim()
  if (!text || chatStreaming.value) return

  const messages = ensureChatMessages()
  const scope = activeChatScope.value
  const history = buildChatHistory(messages)
  const userMessage: ChatMessage = {
    id: nextChatMessageId,
    role: 'user',
    text,
  }
  nextChatMessageId += 1
  const assistantMessage: ChatMessage = {
    id: nextChatMessageId,
    role: 'assistant',
    text: '',
    status: 'streaming',
  }
  nextChatMessageId += 1

  messages.push(userMessage, assistantMessage)
  chatDraft.value = ''
  chatStreaming.value = true
  await scrollChatToBottom()

  try {
    await streamGeminiReply(text, assistantMessage.id, history, scope)
  } catch (error: any) {
    updateChatMessage(scope, assistantMessage.id, (message) => ({
      ...message,
      status: 'failed',
      text: error?.message || 'Gemini chat request failed',
    }))
    await flushChatRender()
  } finally {
    chatStreaming.value = false
  }
}

function onChatDraftKeydown(event: KeyboardEvent) {
  if (event.key !== 'Enter' || event.shiftKey) return
  event.preventDefault()
  sendChatDraft()
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

watch(taskFactsTrigger, () => {
  prefetchGeminiBrief()
}, { immediate: true })

watch(
  () => ({
    taskId: currentTaskId.value,
    status: store.selectedTask?.status || '',
  }),
  (current, previous) => {
    if (!current.taskId || !previous?.taskId) return
    if (current.taskId !== previous.taskId) return
    if (current.status && previous.status && current.status !== previous.status) {
      clearChatMessages(`task:${current.taskId}`)
    }
  },
)

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
      width="440px"
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
              <div class="chat-title-subtitle">{{ geminiModelLabel }}</div>
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
              @click="closeGeminiDialog"
            >
              <span class="chat-close-symbol" aria-hidden="true"></span>
            </el-button>
          </div>
        </div>
      </template>

      <div class="chat-shell">
        <div ref="chatWindowRef" class="chat-window">
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
          <div v-else-if="homeGeminiMessage" class="message-row is-gemini">
            <div class="message-avatar">
              <img :src="geminiIcon" alt="Gemini">
            </div>
            <div class="message-bubble home-message-bubble">
              <p>{{ homeGeminiMessage.text }}</p>
            </div>
          </div>
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
          <div
            v-for="message in activeChatMessages"
            :key="message.id"
            :class="['message-row', message.role === 'user' ? 'is-user' : 'is-gemini']"
          >
            <div v-if="message.role === 'assistant'" class="message-avatar">
              <img :src="geminiIcon" alt="Gemini">
            </div>
            <div
              :class="[
                'message-bubble',
                message.role === 'user' ? 'user-message-bubble' : 'assistant-message-bubble',
                { 'is-streaming': message.status === 'streaming', 'is-failed': message.status === 'failed' },
              ]"
            >
              <p>{{ message.text }}</p>
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
              placeholder="输入消息"
              @keydown="onChatDraftKeydown"
            />
            <el-button
              class="composer-send-button"
              :icon="ArrowUp"
              circle
              :disabled="!canSendChatDraft"
              @click="sendChatDraft"
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
  grid-template-rows: 320px auto;
  overflow: hidden;
  border: 1px solid rgba(16, 24, 40, 0.08);
  border-radius: 8px;
  background: #f7f8fa;
}

.chat-window {
  min-height: 0;
  padding: 16px 14px;
  overflow-x: hidden;
  overflow-y: auto;
}

.chat-loading {
  padding: 4px 2px;
}

.message-row {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  min-width: 0;
}

.message-row.is-user {
  justify-content: flex-end;
  margin-top: 12px;
}

.message-row.is-gemini + .message-row.is-gemini,
.message-row.is-user + .message-row.is-gemini {
  margin-top: 12px;
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
  width: fit-content;
  min-width: 0;
  max-width: min(326px, calc(100% - 48px));
  gap: 12px;
  padding: 12px 14px;
  border: 1px solid rgba(16, 24, 40, 0.06);
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.94);
  box-shadow: 0 8px 18px rgba(16, 24, 40, 0.08);
}

.home-message-bubble {
  min-width: 148px;
  gap: 0;
}

.home-message-bubble p {
  margin: 0;
  color: #26364d;
  line-height: 1.65;
}

.assistant-message-bubble {
  gap: 0;
}

.assistant-message-bubble p {
  margin: 0;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
  word-break: break-word;
  color: #26364d;
  line-height: 1.65;
}

.assistant-message-bubble.is-streaming:empty::after,
.assistant-message-bubble.is-streaming p:empty::after {
  color: #94a3b8;
  content: "Gemini 正在输入...";
}

.assistant-message-bubble.is-failed {
  border-color: rgba(239, 68, 68, 0.18);
  background: rgba(254, 242, 242, 0.96);
}

.user-message-bubble {
  max-width: min(300px, 82%);
  gap: 0;
  border-color: rgba(59, 130, 246, 0.16);
  background: #dbeafe;
  box-shadow: 0 8px 16px rgba(37, 99, 235, 0.1);
}

.user-message-bubble p {
  margin: 0;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
  word-break: break-word;
  color: #15345f;
  line-height: 1.6;
}

.message-section {
  display: grid;
  gap: 5px;
  min-width: 0;
}

.message-section p {
  margin: 0;
  overflow-wrap: anywhere;
  word-break: break-word;
  color: #26364d;
  line-height: 1.65;
}

.message-section ul {
  display: grid;
  gap: 7px;
  min-width: 0;
  margin: 0;
  padding-left: 18px;
  color: #26364d;
  line-height: 1.55;
}

.message-section li {
  min-width: 0;
  overflow-wrap: anywhere;
  word-break: break-word;
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
  min-width: 0;
  padding: 10px 12px;
  border: 1px solid rgba(245, 158, 11, 0.24);
  border-radius: 8px;
  background: rgba(255, 251, 235, 0.82);
  color: #3b2f12;
}

.gate-card strong,
.gate-card span,
.gate-card p {
  min-width: 0;
  overflow-wrap: anywhere;
  word-break: break-word;
}

.gate-card span {
  font-size: 12px;
  color: #936316;
}

.chat-composer {
  padding: 10px;
  border-top: 1px solid rgba(16, 24, 40, 0.08);
  background: rgba(255, 255, 255, 0.88);
}

.composer-box {
  position: relative;
  min-height: 96px;
  padding: 12px 50px 12px 14px;
  border: 1px solid rgba(16, 24, 40, 0.12);
  border-radius: 26px;
  background: rgba(255, 255, 255, 0.95);
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.9);
}

.composer-input {
  height: 100%;
}

.composer-input :deep(.el-textarea__inner) {
  min-height: 68px !important;
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

.composer-send-button {
  position: absolute;
  right: 12px;
  bottom: 12px;
  width: 36px;
  height: 36px;
  border: 0;
  background: #8c939d;
  color: #ffffff;
}

.composer-send-button:not(.is-disabled):hover,
.composer-send-button:not(.is-disabled):focus {
  background: #64748b;
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
