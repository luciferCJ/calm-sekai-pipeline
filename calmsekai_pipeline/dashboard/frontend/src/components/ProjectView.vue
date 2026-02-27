<template>
  <div class="p-8 max-w-6xl mx-auto animate-fade-in">

    <!-- Loading -->
    <div v-if="loading" class="text-sekai-subtle text-sm">Loading project…</div>

    <!-- Error -->
    <div v-else-if="loadError" class="text-sekai-error text-sm">{{ loadError }}</div>

    <template v-else>
      <!-- Header -->
      <div class="flex items-start justify-between gap-4 mb-8">
        <div class="flex-1 min-w-0">
          <div class="flex items-center gap-3 mb-1">
            <button class="text-xs text-sekai-subtle hover:text-sekai-text transition-colors" @click="$router.push('/projects')">
              ← Projects
            </button>
            <StatusBadge :status="project.status" />
            <span class="text-xs px-2 py-0.5 rounded-full bg-sekai-muted/30 text-sekai-subtle">{{ project.aspect_ratio }}</span>
            <span class="text-xs px-2 py-0.5 rounded-full bg-sekai-muted/30 text-sekai-subtle">{{ project.target_duration }}s target</span>
          </div>
          <div class="flex items-center gap-3">
            <h1 v-if="!editingHeader" class="text-xl font-semibold text-sekai-text">{{ project.title }}</h1>
            <input v-else v-model="headerEdit.title" class="input text-xl font-semibold flex-1" @blur="saveHeader" />
            <button
              class="text-xs text-sekai-subtle hover:text-sekai-accent transition-colors"
              @click="toggleHeaderEdit"
            >{{ editingHeader ? 'Done' : 'Edit' }}</button>
          </div>
          <p class="text-sm text-sekai-subtle mt-1">{{ project.theme }} · {{ project.emotion }}</p>
          <p v-if="project.audio_mood" class="text-xs text-sekai-subtle italic mt-0.5 max-w-xl truncate">"{{ editingHeader ? '' : project.audio_mood }}"</p>
          <div v-if="editingHeader" class="mt-2">
            <p class="label mb-1">Audio Mood</p>
            <textarea v-model="headerEdit.audio_mood" class="textarea text-xs" rows="2" @blur="saveHeader" />
          </div>
        </div>
      </div>

      <!-- Error banner -->
      <div v-if="actionError" class="bg-sekai-error/10 border border-sekai-error/30 text-sekai-error text-sm rounded-lg px-4 py-3 mb-6">
        {{ actionError }}
      </div>

      <!-- ================================================================ -->
      <!-- SCENES -->
      <!-- ================================================================ -->
      <div class="mb-8">
        <div class="flex items-center justify-between mb-4">
          <h2 class="text-base font-semibold text-sekai-text">Scenes</h2>
          <button class="btn-ghost text-xs" @click="addScene">+ Add Scene</button>
        </div>

        <div v-if="!scenes.length" class="text-center py-10 text-sekai-subtle text-sm">
          No scenes yet.
        </div>

        <div v-else class="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
          <SceneCard
            v-for="scene in scenes"
            :key="scene.id"
            :scene="scene"
            :project-id="project.id"
            @refresh="load"
            @delete="deleteScene(scene.id)"
          />
        </div>
      </div>

      <!-- ================================================================ -->
      <!-- ASSEMBLY -->
      <!-- ================================================================ -->
      <div class="card mb-6">
        <h2 class="text-base font-semibold text-sekai-text mb-4">Assembly</h2>

        <!-- Audio source tabs -->
        <div class="flex gap-1 mb-4 border-b border-sekai-border">
          <button
            v-for="tab in ['local', 'suno']"
            :key="tab"
            class="px-4 py-2 text-xs font-medium transition-colors border-b-2 -mb-px"
            :class="audioTab === tab
              ? 'border-sekai-accent text-sekai-accent'
              : 'border-transparent text-sekai-subtle hover:text-sekai-text'"
            @click="audioTab = tab"
          >
            {{ tab === 'local' ? 'Local File' : 'Suno AI' }}
          </button>
        </div>

        <!-- Local audio -->
        <div v-if="audioTab === 'local'" class="space-y-3">
          <div class="flex gap-2">
            <input
              v-model="audioFolder"
              class="input flex-1 text-sm"
              placeholder="Paste folder path or click Browse…"
              @change="loadAudioList"
            />
            <button class="btn-ghost text-xs" :disabled="browseLoading" @click="openFolderPicker">
              {{ browseLoading ? '…' : 'Browse' }}
            </button>
          </div>
          <div v-if="audioFiles.length" class="space-y-1 max-h-36 overflow-y-auto">
            <button
              v-for="f in audioFiles"
              :key="f.path"
              class="w-full text-left px-3 py-1.5 rounded-lg text-xs transition-colors"
              :class="selectedAudio?.path === f.path
                ? 'bg-sekai-accent/15 text-sekai-accent'
                : 'text-sekai-subtle hover:text-sekai-text hover:bg-sekai-muted/20'"
              @click="selectedAudio = f"
            >
              {{ f.name }} <span class="text-sekai-muted ml-1">{{ f.size_kb }} KB</span>
            </button>
          </div>
        </div>

        <!-- Suno AI audio -->
        <div v-else class="space-y-3">
          <div v-if="sunoAudio" class="flex items-center gap-3 px-3 py-2 rounded-lg bg-sekai-accent/10 border border-sekai-accent/30">
            <span class="text-xs text-sekai-accent">✓ {{ sunoAudio.name }} ({{ sunoAudio.size_kb }} KB)</span>
          </div>
          <div v-else class="text-xs text-sekai-subtle">No Suno audio generated yet.</div>
          <button
            class="btn-ghost text-xs flex items-center gap-2"
            :disabled="assemblyJobRunning"
            @click="runSunoAudio"
          >
            <span v-if="sunoJobRunning" class="w-3 h-3 border-2 border-sekai-accent border-t-transparent rounded-full animate-spin" />
            {{ sunoJobRunning ? 'Generating…' : 'Generate with Suno AI' }}
          </button>
          <p v-if="sunoError" class="text-xs text-sekai-error">{{ sunoError }}</p>
        </div>

        <!-- Assemble button -->
        <div class="flex items-center gap-3 mt-4 pt-4 border-t border-sekai-border">
          <button
            class="btn-primary flex items-center gap-2"
            :disabled="!effectiveAudioPath || assemblyJobRunning || !allScenesVideoReady"
            @click="runAssemble"
          >
            <span v-if="assemblyJobRunning" class="w-3.5 h-3.5 border-2 border-sekai-bg border-t-transparent rounded-full animate-spin" />
            {{ assemblyJobRunning ? 'Assembling…' : 'Assemble' }}
          </button>
          <p v-if="!allScenesVideoReady" class="text-xs text-sekai-subtle">All scenes must have video generated first.</p>
          <p v-else-if="!effectiveAudioPath" class="text-xs text-sekai-subtle">Select or generate audio first.</p>
          <p v-if="assemblyError" class="text-xs text-sekai-error">{{ assemblyError }}</p>
        </div>

        <!-- Final video preview -->
        <div v-if="finalVideoExists" class="mt-4">
          <video
            controls
            class="w-full rounded-lg max-h-96"
            :src="`/api/projects/${project.id}/video/final?t=${videoKey}`"
          />
        </div>
      </div>

      <!-- ================================================================ -->
      <!-- SEO -->
      <!-- ================================================================ -->
      <div class="card mb-6">
        <div class="flex items-center justify-between mb-4">
          <h2 class="text-base font-semibold text-sekai-text">SEO</h2>
          <div class="flex gap-2">
            <button
              class="btn-ghost text-xs flex items-center gap-2"
              :disabled="seoJobRunning || project.status === 'draft'"
              @click="runSeo"
            >
              <span v-if="seoJobRunning" class="w-3 h-3 border-2 border-sekai-accent border-t-transparent rounded-full animate-spin" />
              {{ seoJobRunning ? 'Generating…' : 'Generate SEO' }}
            </button>
          </div>
        </div>

        <div v-if="!metadata" class="text-xs text-sekai-subtle">
          {{ project.status === 'draft' ? 'Assemble the project first, then generate SEO.' : 'Run SEO generation to create title, description, and hashtags.' }}
        </div>

        <div v-else class="space-y-3">
          <!-- Title -->
          <div>
            <p class="label mb-1">Title</p>
            <input
              v-model="metadata.title"
              class="input text-sm w-full"
              @blur="saveMeta('title', metadata.title)"
            />
          </div>
          <!-- Description -->
          <div>
            <p class="label mb-1">Description</p>
            <textarea
              v-model="metadata.description"
              class="textarea text-sm"
              rows="5"
              @blur="saveMeta('description', metadata.description)"
            />
          </div>
          <!-- Hashtags -->
          <div>
            <p class="label mb-1">Hashtags</p>
            <input
              v-model="hashtagsText"
              class="input text-sm w-full font-mono"
              @blur="saveMeta('hashtags', hashtagsText.split(' ').filter(Boolean))"
            />
          </div>
        </div>
      </div>

      <!-- ================================================================ -->
      <!-- UPLOAD -->
      <!-- ================================================================ -->
      <div class="card">
        <div class="flex items-center justify-between">
          <div>
            <h2 class="text-base font-semibold text-sekai-text">Upload to YouTube</h2>
            <p class="text-xs text-sekai-subtle mt-0.5">Requires assembly_done + SEO metadata</p>
          </div>
          <button
            class="btn-primary flex items-center gap-2"
            :disabled="!canUpload || uploadJobRunning"
            @click="runUpload"
          >
            <span v-if="uploadJobRunning" class="w-3.5 h-3.5 border-2 border-sekai-bg border-t-transparent rounded-full animate-spin" />
            {{ uploadJobRunning ? 'Uploading…' : project.status === 'uploaded' ? 'Re-upload' : 'Upload' }}
          </button>
        </div>
        <p v-if="uploadError" class="text-xs text-sekai-error mt-2">{{ uploadError }}</p>
        <p v-if="project.status === 'uploaded'" class="text-xs text-sekai-accent mt-2">Uploaded ✓</p>
      </div>
    </template>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useRoute } from 'vue-router'
import StatusBadge from './StatusBadge.vue'
import SceneCard   from './SceneCard.vue'

const route = useRoute()
const pid   = route.params.id

// -------------------------------------------------------------------------
// State
// -------------------------------------------------------------------------

const loading     = ref(true)
const loadError   = ref('')
const actionError = ref('')
const project     = ref({})
const scenes      = ref([])
const metadata    = ref(null)
const videoKey    = ref(0)
const finalVideoExists = ref(false)

// Header edit
const editingHeader = ref(false)
const headerEdit    = ref({ title: '', audio_mood: '' })

// Audio
const audioTab     = ref('local')
const audioFolder  = ref('')
const audioFiles   = ref([])
const selectedAudio = ref(null)
const browseLoading = ref(false)
const sunoAudio    = ref(null)
const sunoError    = ref('')

// Job states
const assemblyJobRunning = ref(false)
const assemblyError      = ref('')
const sunoJobRunning     = ref(false)
const seoJobRunning      = ref(false)
const uploadJobRunning   = ref(false)
const uploadError        = ref('')

let _projectPollTimer = null

// -------------------------------------------------------------------------
// Computed
// -------------------------------------------------------------------------

const allScenesVideoReady = computed(() =>
  scenes.value.length > 0 &&
  scenes.value.every(s => ['video_done', 'assembly_done'].includes(s.status))
)

const effectiveAudioPath = computed(() => {
  if (audioTab.value === 'local') return selectedAudio.value?.path || null
  return sunoAudio.value?.path || null
})

const hashtagsText = computed({
  get: () => (metadata.value?.hashtags || []).join(' '),
  set: (v) => { if (metadata.value) metadata.value.hashtags = v.split(' ').filter(Boolean) }
})

const canUpload = computed(() =>
  ['assembly_done', 'seo_done', 'uploaded'].includes(project.value.status)
)

// -------------------------------------------------------------------------
// Load
// -------------------------------------------------------------------------

async function load() {
  try {
    const r = await fetch(`/api/projects/${pid}`)
    if (!r.ok) throw new Error('Project not found')
    const data = await r.json()
    project.value = data
    scenes.value  = data.scenes || []

    // Check final video
    finalVideoExists.value = ['assembly_done', 'seo_done', 'uploaded'].includes(data.status)
    if (finalVideoExists.value) videoKey.value++

    // Try to load metadata
    await loadMetadata()

    // Check Suno audio
    await checkSunoAudio()
  } catch (e) {
    loadError.value = e.message
  } finally {
    loading.value = false
  }
}

async function loadMetadata() {
  try {
    const r = await fetch(`/api/projects/${pid}/metadata`)
    if (r.ok) metadata.value = await r.json()
  } catch { /* not available yet */ }
}

// -------------------------------------------------------------------------
// Header edit
// -------------------------------------------------------------------------

function toggleHeaderEdit() {
  if (!editingHeader.value) {
    headerEdit.value = {
      title:      project.value.title,
      audio_mood: project.value.audio_mood || '',
    }
  }
  editingHeader.value = !editingHeader.value
}

async function saveHeader() {
  try {
    const r = await fetch(`/api/projects/${pid}`, {
      method:  'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify(headerEdit.value),
    })
    if (!r.ok) throw new Error((await r.json()).detail)
    const updated = await r.json()
    project.value.title      = updated.title
    project.value.audio_mood = updated.audio_mood
  } catch (e) {
    actionError.value = e.message
    setTimeout(() => { actionError.value = '' }, 3000)
  }
}

// -------------------------------------------------------------------------
// Scene management
// -------------------------------------------------------------------------

async function addScene() {
  try {
    const r = await fetch(`/api/projects/${pid}/scenes`, { method: 'POST' })
    if (!r.ok) throw new Error((await r.json()).detail)
    await load()
  } catch (e) {
    actionError.value = e.message
  }
}

async function deleteScene(sceneId) {
  try {
    await fetch(`/api/projects/${pid}/scenes/${sceneId}`, { method: 'DELETE' })
    await load()
  } catch (e) {
    actionError.value = e.message
  }
}

// -------------------------------------------------------------------------
// Audio
// -------------------------------------------------------------------------

async function openFolderPicker() {
  browseLoading.value = true
  try {
    const r = await fetch('/api/browse/folder', { method: 'POST' })
    const d = await r.json()
    if (d.path) {
      audioFolder.value = d.path
      await loadAudioList()
    }
  } catch { /* ignore */ } finally {
    browseLoading.value = false
  }
}

async function loadAudioList() {
  if (!audioFolder.value) return
  try {
    const r = await fetch(`/api/audio/list?folder=${encodeURIComponent(audioFolder.value)}`)
    if (!r.ok) return
    const d = await r.json()
    audioFiles.value = d.files || []
  } catch { /* ignore */ }
}

async function checkSunoAudio() {
  try {
    const r = await fetch(`/api/projects/${pid}/audio/info`)
    const d = await r.json()
    if (d.exists) {
      sunoAudio.value = d
      audioTab.value  = 'suno'
    }
  } catch { /* ignore */ }
}

async function runSunoAudio() {
  sunoError.value = ''
  try {
    const r = await fetch(`/api/projects/${pid}/run/audio`, { method: 'POST' })
    if (!r.ok) throw new Error((await r.json()).detail)
    sunoJobRunning.value = true
    startProjectPoll()
  } catch (e) {
    sunoError.value = e.message
  }
}

// -------------------------------------------------------------------------
// Assembly
// -------------------------------------------------------------------------

async function runAssemble() {
  assemblyError.value = ''
  try {
    const r = await fetch(`/api/projects/${pid}/run/assemble`, {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify({ audio_path: effectiveAudioPath.value }),
    })
    if (!r.ok) throw new Error((await r.json()).detail)
    assemblyJobRunning.value = true
    startProjectPoll()
  } catch (e) {
    assemblyError.value = e.message
  }
}

// -------------------------------------------------------------------------
// SEO
// -------------------------------------------------------------------------

async function runSeo() {
  try {
    const r = await fetch(`/api/projects/${pid}/run/seo`, { method: 'POST' })
    if (!r.ok) throw new Error((await r.json()).detail)
    seoJobRunning.value = true
    startProjectPoll()
  } catch (e) {
    actionError.value = e.message
  }
}

async function saveMeta(field, value) {
  try {
    await fetch(`/api/projects/${pid}/metadata`, {
      method:  'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify({ field, value }),
    })
  } catch { /* ignore */ }
}

// -------------------------------------------------------------------------
// Upload
// -------------------------------------------------------------------------

async function runUpload() {
  uploadError.value = ''
  try {
    const r = await fetch(`/api/projects/${pid}/upload`, { method: 'POST' })
    if (!r.ok) throw new Error((await r.json()).detail)
    uploadJobRunning.value = true
    startProjectPoll()
  } catch (e) {
    uploadError.value = e.message
  }
}

// -------------------------------------------------------------------------
// Project-level job polling (assemble, seo, audio, upload)
// -------------------------------------------------------------------------

async function pollProjectJob() {
  try {
    const r = await fetch(`/api/jobs/${pid}`)
    const d = await r.json()
    if (!d) {
      resetProjectJobState()
      return
    }

    const { stage, running, error } = d

    if (error) {
      if (stage === 'assemble') assemblyError.value = `Assemble failed: ${error}`
      if (stage === 'upload')   uploadError.value   = `Upload failed: ${error}`
      if (stage === 'audio')    sunoError.value     = `Audio failed: ${error}`
      resetProjectJobState()
      stopProjectPoll()
      return
    }

    assemblyJobRunning.value = running && stage === 'assemble'
    seoJobRunning.value      = running && stage === 'seo'
    sunoJobRunning.value     = running && stage === 'audio'
    uploadJobRunning.value   = running && stage === 'upload'

    if (!running) {
      stopProjectPoll()
      if (stage === 'audio') await checkSunoAudio()
      await load()
    }
  } catch { /* ignore */ }
}

function startProjectPoll() {
  stopProjectPoll()
  _projectPollTimer = setInterval(pollProjectJob, 3000)
}

function stopProjectPoll() {
  if (_projectPollTimer) { clearInterval(_projectPollTimer); _projectPollTimer = null }
}

function resetProjectJobState() {
  assemblyJobRunning.value = false
  seoJobRunning.value      = false
  sunoJobRunning.value     = false
  uploadJobRunning.value   = false
}

// -------------------------------------------------------------------------
// Lifecycle
// -------------------------------------------------------------------------

onMounted(async () => {
  await load()
  // Resume any running job
  const r = await fetch(`/api/jobs/${pid}`)
  const d = await r.json()
  if (d && d.running) {
    assemblyJobRunning.value = d.stage === 'assemble'
    seoJobRunning.value      = d.stage === 'seo'
    sunoJobRunning.value     = d.stage === 'audio'
    uploadJobRunning.value   = d.stage === 'upload'
    startProjectPoll()
  }
})

onUnmounted(stopProjectPoll)
</script>
