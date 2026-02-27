<template>
  <div class="card flex flex-col gap-3 animate-fade-in">

    <!-- Header: scene number + status + edit -->
    <div class="flex items-start justify-between gap-2">
      <div class="flex-1 min-w-0">
        <div class="flex items-center gap-2">
          <span class="text-xs font-mono text-sekai-muted shrink-0">Scene {{ local.order }}</span>
          <span v-if="jobRunning" class="w-3 h-3 border-2 border-sekai-accent border-t-transparent rounded-full animate-spin shrink-0" />
        </div>
        <p v-if="!editing" class="text-xs text-sekai-subtle mt-1 leading-relaxed">{{ local.description || '(no description)' }}</p>
        <textarea
          v-else
          v-model="local.description"
          class="textarea text-xs mt-1"
          rows="2"
          placeholder="Scene description…"
          @blur="save('description', local.description)"
        />
      </div>
      <div class="flex items-center gap-1.5 shrink-0">
        <button
          class="text-xs text-sekai-subtle hover:text-sekai-accent transition-colors px-1"
          @click="editing = !editing"
        >
          {{ editing ? 'Done' : 'Edit' }}
        </button>
        <span :class="statusClass">{{ statusLabel }}</span>
      </div>
    </div>

    <!-- Image thumbnail -->
    <div class="relative">
      <img
        v-if="imageExists"
        :src="imageUrl"
        class="w-full rounded-lg object-cover"
        :style="aspectStyle"
        :key="imageKey"
      />
      <div
        v-else
        class="w-full rounded-lg bg-sekai-muted/20 flex items-center justify-center"
        :style="aspectStyle"
      >
        <span class="text-sekai-muted text-xs">No image yet</span>
      </div>
    </div>

    <!-- Duration pill -->
    <div class="flex gap-2 flex-wrap">
      <template v-if="!editing">
        <span class="text-xs px-2 py-0.5 rounded-full bg-sekai-muted/30 text-sekai-subtle">
          {{ local.duration }}s
        </span>
        <span class="text-xs px-2 py-0.5 rounded-full bg-sekai-muted/30 text-sekai-subtle">
          {{ local.aspect_ratio }}
        </span>
      </template>
      <template v-else>
        <div class="flex items-center gap-2">
          <label class="text-xs text-sekai-muted">Duration (s)</label>
          <input
            v-model.number="local.duration"
            type="number"
            min="5"
            max="60"
            class="input text-xs py-0.5 w-20"
            @blur="save('duration', local.duration)"
          />
        </div>
      </template>
    </div>

    <!-- Image prompt (edit only) -->
    <div v-if="editing" class="space-y-0.5">
      <p class="label">Image Prompt</p>
      <textarea
        v-model="local.image_prompt"
        class="textarea text-xs"
        rows="4"
        @blur="save('image_prompt', local.image_prompt)"
      />
    </div>

    <!-- Video motion (edit only) -->
    <div v-if="editing" class="space-y-0.5">
      <p class="label">Video Motion</p>
      <textarea
        v-model="local.video_motion_instruction"
        class="textarea text-xs"
        rows="2"
        @blur="save('video_motion_instruction', local.video_motion_instruction)"
      />
    </div>

    <!-- Save feedback -->
    <p v-if="saveMsg" class="text-xs text-sekai-accent -mt-1">{{ saveMsg }}</p>
    <p v-if="jobError" class="text-xs text-sekai-error -mt-1">{{ jobError }}</p>

    <!-- Action buttons -->
    <div class="flex gap-2 mt-auto pt-1">
      <button
        class="btn-primary flex-1 text-xs py-1.5 flex items-center justify-center gap-1.5"
        :disabled="!canRunImage || jobRunning"
        @click="runImage"
      >
        <span v-if="jobStage === 'image' && jobRunning" class="w-3 h-3 border-2 border-sekai-bg border-t-transparent rounded-full animate-spin" />
        {{ jobStage === 'image' && jobRunning ? 'Generating…' : 'Run Image' }}
      </button>
      <button
        class="btn-ghost flex-1 text-xs py-1.5 flex items-center justify-center gap-1.5"
        :disabled="!canRunVideo || jobRunning"
        @click="runVideo"
      >
        <span v-if="jobStage === 'video' && jobRunning" class="w-3 h-3 border-2 border-sekai-accent border-t-transparent rounded-full animate-spin" />
        {{ jobStage === 'video' && jobRunning ? 'Generating…' : 'Run Video' }}
      </button>
      <button
        v-if="canDelete"
        class="text-xs text-sekai-error hover:bg-sekai-error/10 px-2 py-1.5 rounded-lg transition-colors"
        title="Delete scene"
        @click="$emit('delete')"
      >✕</button>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, computed, watch, onMounted, onUnmounted } from 'vue'

const props = defineProps({
  scene:     { type: Object, required: true },
  projectId: { type: String, required: true },
})
const emit = defineEmits(['refresh', 'delete'])

const local    = reactive(JSON.parse(JSON.stringify(props.scene)))
const editing  = ref(false)
const saveMsg  = ref('')
const jobError = ref('')
const imageKey = ref(0)

// Sync local when parent refreshes
watch(() => props.scene, (s) => {
  Object.assign(local, JSON.parse(JSON.stringify(s)))
  imageKey.value++
}, { deep: true })

// -----------------------------------------------------------------------
// Derived state
// -----------------------------------------------------------------------

const imageUrl   = computed(() => `/api/projects/${props.projectId}/scenes/${props.scene.id}/image?t=${imageKey.value}`)
const imageExists = computed(() => ['image_done', 'video_done'].includes(local.status))

const canRunImage = computed(() => local.status === 'pending')
const canRunVideo = computed(() => local.status === 'image_done')
const canDelete   = computed(() => local.status === 'pending')

const aspectStyle = computed(() => {
  const ar = local.aspect_ratio || '9:16'
  if (ar === '16:9') return { aspectRatio: '16/9', maxHeight: '160px' }
  if (ar === '1:1')  return { aspectRatio: '1/1',  maxHeight: '200px' }
  return { aspectRatio: '9/16', maxHeight: '220px' }
})

const STATUS_MAP = {
  pending:    { cls: 'badge-pending',  label: 'Pending'      },
  image_done: { cls: 'badge-done',     label: 'Image ready'  },
  video_done: { cls: 'badge-done',     label: 'Video ready'  },
}
const statusClass = computed(() => STATUS_MAP[local.status]?.cls ?? 'badge-pending')
const statusLabel = computed(() => STATUS_MAP[local.status]?.label ?? local.status)

// -----------------------------------------------------------------------
// Job polling
// -----------------------------------------------------------------------

const jobRunning = ref(false)
const jobStage   = ref('')
let _pollTimer   = null

async function pollJob() {
  try {
    const r = await fetch(`/api/jobs/${props.scene.id}`)
    const d = await r.json()
    if (!d) {
      jobRunning.value = false
      return
    }
    jobRunning.value = d.running
    jobStage.value   = d.stage
    if (d.error) {
      jobError.value   = `Stage '${d.stage}' failed: ${d.error}`
      jobRunning.value = false
    } else if (!d.running) {
      emit('refresh')
    }
  } catch { /* ignore network errors during polling */ }
}

function startPolling() {
  stopPolling()
  _pollTimer = setInterval(pollJob, 3000)
}

function stopPolling() {
  if (_pollTimer) { clearInterval(_pollTimer); _pollTimer = null }
}

// -----------------------------------------------------------------------
// Run image / video
// -----------------------------------------------------------------------

async function runImage() {
  jobError.value = ''
  try {
    const r = await fetch(
      `/api/projects/${props.projectId}/scenes/${props.scene.id}/run/image`,
      { method: 'POST' }
    )
    if (!r.ok) throw new Error((await r.json()).detail)
    jobRunning.value = true
    jobStage.value   = 'image'
    startPolling()
  } catch (e) {
    jobError.value = e.message
  }
}

async function runVideo() {
  jobError.value = ''
  try {
    const r = await fetch(
      `/api/projects/${props.projectId}/scenes/${props.scene.id}/run/video`,
      { method: 'POST' }
    )
    if (!r.ok) throw new Error((await r.json()).detail)
    jobRunning.value = true
    jobStage.value   = 'video'
    startPolling()
  } catch (e) {
    jobError.value = e.message
  }
}

// -----------------------------------------------------------------------
// Field save (blur-debounced)
// -----------------------------------------------------------------------

let _saveTimer = null
async function save(field, value) {
  clearTimeout(_saveTimer)
  _saveTimer = setTimeout(async () => {
    try {
      const r = await fetch(
        `/api/projects/${props.projectId}/scenes/${props.scene.id}`,
        {
          method:  'PATCH',
          headers: { 'Content-Type': 'application/json' },
          body:    JSON.stringify({ [field]: value }),
        }
      )
      if (!r.ok) throw new Error((await r.json()).detail)
      saveMsg.value = 'Saved ✓'
      setTimeout(() => { saveMsg.value = '' }, 1500)
    } catch (e) {
      saveMsg.value = `Error: ${e.message}`
    }
  }, 300)
}

// Check if a job is already running on mount
onMounted(async () => {
  const r = await fetch(`/api/jobs/${props.scene.id}`)
  const d = await r.json()
  if (d && d.running) {
    jobRunning.value = true
    jobStage.value   = d.stage
    startPolling()
  }
})

onUnmounted(stopPolling)
</script>
