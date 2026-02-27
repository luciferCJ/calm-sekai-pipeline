<template>
  <div v-if="loading" class="flex items-center justify-center h-full text-sekai-subtle text-sm">
    Loading…
  </div>

  <div v-else-if="concept" class="p-8 max-w-6xl mx-auto animate-fade-in">
    <!-- Header -->
    <div class="flex items-center gap-4 mb-8">
      <button class="text-sekai-subtle hover:text-sekai-text text-sm transition-colors" @click="$router.back()">
        ← Back
      </button>
      <div class="flex-1">
        <h1 class="text-xl font-semibold">{{ concept.theme }}</h1>
        <p class="text-sm text-sekai-subtle mt-0.5">{{ concept.emotion }} · {{ fmtFormat }}</p>
      </div>
      <StatusBadge :status="concept.status" />
    </div>

    <!-- Global error -->
    <div v-if="globalError" class="bg-sekai-error/10 border border-sekai-error/30 text-sekai-error text-sm rounded-lg px-4 py-3 mb-6">
      {{ globalError }}
    </div>

    <div class="grid grid-cols-1 lg:grid-cols-2 gap-6">

      <!-- ===== LEFT COLUMN: Pipeline stages ===== -->
      <div class="space-y-4">

        <!-- Stage 1: Image generation -->
        <StageCard
          title="Image Generation"
          :status="imageStatus"
          :canRun="concept.status === 'approved'"
          :running="jobStage === 'image' && jobRunning"
          @run="runImage"
        >
          <img
            v-if="concept.status !== 'approved' && concept.status !== 'pending_approval' && concept.status !== 'rejected'"
            :src="`/api/concepts/${concept.id}/image`"
            class="w-full rounded-lg object-cover aspect-[9/16] max-h-48 object-top"
            :key="imageKey"
          />
        </StageCard>

        <!-- Stage 2: Video generation -->
        <StageCard
          title="Video Generation"
          subtitle="~5–10 min via Grok"
          :status="videoStatus"
          :canRun="concept.status === 'image_done'"
          :running="jobStage === 'video' && jobRunning"
          @run="runVideo"
        />

        <!-- Stage 3: SEO generation (can run in parallel with video) -->
        <StageCard
          title="SEO Metadata"
          :status="seoStatus"
          :canRun="['approved','image_done','video_done','assembly_done'].includes(concept.status)"
          :running="jobStage === 'seo' && jobRunning"
          @run="runSeo"
        />

        <!-- Stage 4: Assembly -->
        <div class="card">
          <div class="flex items-center justify-between mb-4">
            <div>
              <p class="text-sm font-medium text-sekai-text">Assembly</p>
              <p class="text-xs text-sekai-subtle mt-0.5">Merge video + audio · FFmpeg</p>
            </div>
            <StatusBadge :status="assemblyStatusLabel" />
          </div>

          <!-- Audio source tab switcher -->
          <div class="flex rounded-lg overflow-hidden border border-sekai-border mb-3">
            <button
              class="flex-1 text-xs py-1.5 transition-colors"
              :class="audioTab === 'local'
                ? 'bg-sekai-accent text-white'
                : 'text-sekai-subtle hover:text-sekai-text'"
              @click="audioTab = 'local'"
            >
              Local File
            </button>
            <button
              class="flex-1 text-xs py-1.5 transition-colors"
              :class="audioTab === 'suno'
                ? 'bg-sekai-accent text-white'
                : 'text-sekai-subtle hover:text-sekai-text'"
              @click="audioTab = 'suno'"
            >
              Suno AI
            </button>
          </div>

          <!-- Local File tab -->
          <div v-if="audioTab === 'local'" class="space-y-3">
            <div>
              <p class="label mb-1.5">Audio folder</p>
              <div class="flex gap-2">
                <input
                  v-model="audioFolder"
                  class="input"
                  placeholder="C:/Users/.../Music"
                  @keydown.enter="loadAudioList"
                />
                <button
                  class="btn-ghost shrink-0 text-xs"
                  :disabled="browseLoading"
                  @click="openFolderPicker"
                >
                  {{ browseLoading ? '…' : 'Browse' }}
                </button>
              </div>
            </div>

            <!-- Audio file list -->
            <div v-if="audioFiles.length" class="space-y-1 max-h-40 overflow-y-auto">
              <button
                v-for="f in audioFiles"
                :key="f.path"
                class="w-full text-left px-3 py-2 rounded-lg text-xs transition-colors flex items-center justify-between gap-2"
                :class="selectedAudio?.path === f.path
                  ? 'bg-sekai-accent/20 text-sekai-accent border border-sekai-accent/30'
                  : 'text-sekai-text hover:bg-sekai-surface border border-transparent'"
                @click="selectedAudio = f"
              >
                <span class="truncate">{{ f.name }}</span>
                <span class="text-sekai-subtle shrink-0">{{ f.size_kb }}KB</span>
              </button>
            </div>
            <p v-else-if="audioFolder && !audioLoading" class="text-xs text-sekai-subtle">
              No audio files found in that folder.
            </p>
          </div>

          <!-- Suno AI tab -->
          <div v-else class="space-y-3">
            <!-- Audio mood preview -->
            <div class="rounded-lg bg-sekai-surface px-3 py-2">
              <p class="text-xs text-sekai-subtle mb-0.5">Audio mood</p>
              <p class="text-xs text-sekai-text">{{ concept.audio_mood || '—' }}</p>
            </div>

            <!-- Already generated -->
            <div
              v-if="sunoAudio"
              class="flex items-center justify-between px-3 py-2 rounded-lg bg-sekai-accent/10 border border-sekai-accent/30"
            >
              <div>
                <p class="text-xs font-medium text-sekai-accent">{{ sunoAudio.name }}</p>
                <p class="text-xs text-sekai-subtle">{{ sunoAudio.size_kb }} KB · ready</p>
              </div>
              <span class="text-sekai-accent text-sm">✓</span>
            </div>

            <!-- Suno error -->
            <p v-if="sunoError" class="text-xs text-sekai-error">{{ sunoError }}</p>

            <!-- Generate button -->
            <button
              class="btn-primary w-full text-sm"
              :disabled="jobStage === 'audio' && jobRunning"
              @click="runSunoAudio"
            >
              <span v-if="jobStage === 'audio' && jobRunning">Generating… (up to 5 min)</span>
              <span v-else-if="sunoAudio">Regenerate with Suno</span>
              <span v-else>Generate with Suno AI</span>
            </button>
          </div>

          <!-- Breathing zoom toggle (shared) -->
          <label class="flex items-center gap-2 cursor-pointer select-none mt-3">
            <div
              class="w-8 h-4.5 rounded-full transition-colors relative"
              :class="breathingZoom ? 'bg-sekai-accent' : 'bg-sekai-muted'"
              @click="breathingZoom = !breathingZoom"
            >
              <div
                class="absolute top-0.5 w-3.5 h-3.5 bg-white rounded-full shadow transition-transform"
                :class="breathingZoom ? 'translate-x-4' : 'translate-x-0.5'"
              />
            </div>
            <span class="text-xs text-sekai-text">Breathing zoom (+3% crop)</span>
          </label>

          <!-- Assemble button (shared) -->
          <button
            class="btn-primary w-full text-sm mt-3"
            :disabled="!effectiveAudioPath || !['video_done','assembly_done','seo_done'].includes(concept.status) || (jobStage === 'assemble' && jobRunning)"
            @click="runAssemble"
          >
            <span v-if="jobStage === 'assemble' && jobRunning">Assembling…</span>
            <span v-else>Assemble Video</span>
          </button>
        </div>
      </div>

      <!-- ===== RIGHT COLUMN: Preview + SEO editor ===== -->
      <div class="space-y-4">

        <!-- Video preview -->
        <div class="card">
          <p class="label mb-3">Preview</p>
          <div class="relative bg-black rounded-lg overflow-hidden aspect-[9/16] max-h-80 mx-auto w-fit">
            <video
              v-if="concept.status === 'assembly_done' || concept.status === 'seo_done' || concept.status === 'uploaded'"
              :src="`/api/concepts/${concept.id}/video/final?t=${videoKey}`"
              :poster="`/api/concepts/${concept.id}/thumbnail`"
              controls
              class="h-full w-auto"
            />
            <img
              v-else-if="concept.status !== 'approved' && concept.status !== 'pending_approval'"
              :src="`/api/concepts/${concept.id}/image?t=${imageKey}`"
              class="h-full w-auto object-cover"
            />
            <div v-else class="flex items-center justify-center h-full w-40 text-sekai-subtle text-xs text-center p-4">
              Preview will appear after image generation
            </div>
          </div>
        </div>

        <!-- SEO editor -->
        <div v-if="meta" class="card space-y-4">
          <p class="label">SEO Metadata</p>

          <!-- Title -->
          <div>
            <div class="flex items-center justify-between mb-1.5">
              <p class="label">Title</p>
              <span
                class="text-xs"
                :class="(meta.title || '').length > 60 ? 'text-sekai-error' : 'text-sekai-subtle'"
              >
                {{ (meta.title || '').length }}/60
              </span>
            </div>
            <input
              v-model="meta.title"
              class="input"
              maxlength="100"
              @blur="saveField('title', meta.title)"
            />
          </div>

          <!-- Description -->
          <div>
            <p class="label mb-1.5">Description</p>
            <textarea
              v-model="meta.description"
              class="textarea"
              rows="4"
              @blur="saveField('description', meta.description)"
            />
          </div>

          <!-- Hashtags -->
          <div>
            <p class="label mb-1.5">Hashtags</p>
            <div class="flex flex-wrap gap-1.5 mb-2">
              <span
                v-for="(tag, i) in meta.hashtags"
                :key="i"
                class="text-xs px-2 py-0.5 rounded-full bg-sekai-accent/10 text-sekai-accent border border-sekai-accent/20 flex items-center gap-1"
              >
                {{ tag }}
                <button class="text-sekai-subtle hover:text-sekai-error" @click="removeHashtag(i)">×</button>
              </span>
            </div>
            <input
              v-model="newTag"
              class="input text-xs"
              placeholder="Add hashtag (press Enter)"
              @keydown.enter="addHashtag"
            />
          </div>

          <!-- Regenerate SEO -->
          <button
            class="btn-ghost w-full text-xs"
            :disabled="jobStage === 'seo' && jobRunning"
            @click="runSeo"
          >
            Regenerate SEO
          </button>
        </div>

        <!-- Upload button -->
        <div class="card">
          <p class="label mb-3">YouTube Upload</p>
          <p class="text-xs text-sekai-subtle mb-4">
            Requires assembly + SEO to be complete. Uploads as a YouTube Short (9:16, public).
          </p>
          <button
            class="btn-success w-full"
            :disabled="!canUpload || uploading"
            @click="uploadToYouTube"
          >
            {{ uploading ? 'Uploading…' : '↑ Upload to YouTube' }}
          </button>
        </div>

      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useRoute } from 'vue-router'
import StatusBadge from './StatusBadge.vue'
import StageCard   from './StageCard.vue'

const route = useRoute()
const id    = route.params.id

const concept    = ref(null)
const meta       = ref(null)
const loading    = ref(true)
const globalError = ref('')

// Job polling
const jobRunning = ref(false)
const jobStage   = ref('')
const jobError   = ref('')
let   pollTimer  = null

// Local audio browser
const audioFolder   = ref('')
const audioFiles    = ref([])
const audioLoading  = ref(false)
const selectedAudio = ref(null)
const browseLoading = ref(false)

// Suno AI audio
const audioTab       = ref('local')   // 'local' | 'suno'
const sunoAudio      = ref(null)      // { path, name, size_kb } when generated
const sunoError      = ref('')

// Shared assembly options
const breathingZoom = ref(true)

// SEO editing
const newTag = ref('')

// Media cache-busting keys
const imageKey = ref(Date.now())
const videoKey = ref(Date.now())

// Upload
const uploading = ref(false)

// -----------------------------------------------------------------------
// Computed helpers
// -----------------------------------------------------------------------

const fmtFormat = computed(() => concept.value?.format === 'shorts_10s' ? '10s Short' : '30s Short')

const imageStatus = computed(() => {
  const s = concept.value?.status
  if (s === 'pending_approval' || s === 'approved') return s === 'approved' ? 'ready' : 'locked'
  return 'done'
})

const videoStatus = computed(() => {
  const s = concept.value?.status
  if (['image_done'].includes(s)) return 'ready'
  if (['video_done', 'assembly_done', 'seo_done', 'uploaded'].includes(s)) return 'done'
  return 'locked'
})

const seoStatus = computed(() => {
  const s = concept.value?.status
  if (s === 'seo_done' || s === 'uploaded') return 'done'
  return 'ready'
})

const assemblyStatusLabel = computed(() => {
  const s = concept.value?.status
  if (s === 'assembly_done' || s === 'seo_done' || s === 'uploaded') return 'done'
  if (jobStage.value === 'assemble' && jobRunning.value) return 'running'
  return 'pending'
})

const canUpload = computed(() => {
  const s = concept.value?.status
  return ['assembly_done', 'seo_done'].includes(s)
})

/** The audio path that will be sent to the assemble endpoint. */
const effectiveAudioPath = computed(() =>
  audioTab.value === 'local'
    ? (selectedAudio.value?.path ?? null)
    : (sunoAudio.value?.path ?? null)
)

// -----------------------------------------------------------------------
// Data loading
// -----------------------------------------------------------------------

async function load() {
  try {
    const r = await fetch(`/api/concepts/${id}`)
    if (!r.ok) throw new Error('Not found')
    concept.value = await r.json()

    imageKey.value = Date.now()
    if (concept.value.status === 'assembly_done' || concept.value.status === 'seo_done') {
      videoKey.value = Date.now()
    }
  } catch (e) {
    globalError.value = 'Could not load concept.'
  } finally {
    loading.value = false
  }
}

async function loadMeta() {
  try {
    const r = await fetch(`/api/concepts/${id}/metadata`)
    if (r.ok) meta.value = await r.json()
  } catch { /* SEO not generated yet */ }
}

async function pollJob() {
  try {
    const r = await fetch(`/api/jobs/${id}`)
    const data = await r.json()
    if (!data) { jobRunning.value = false; return }

    jobStage.value   = data.stage
    jobRunning.value = data.running
    jobError.value   = data.error || ''

    if (!data.running) {
      await load()
      await loadMeta()
      if (data.error) {
        if (data.stage === 'audio') {
          sunoError.value = `Suno generation failed: ${data.error}`
        } else {
          globalError.value = `Stage '${data.stage}' failed: ${data.error}`
        }
      } else if (data.stage === 'audio') {
        // Audio job finished successfully — fetch the file info
        await checkSunoAudio()
      }
    }
  } catch { /* ignore poll errors */ }
}

function startPolling() {
  if (pollTimer) return
  pollTimer = setInterval(pollJob, 3000)
}

// -----------------------------------------------------------------------
// Audio browser (local)
// -----------------------------------------------------------------------

async function loadAudioList() {
  if (!audioFolder.value.trim()) return
  audioLoading.value = true
  try {
    const r = await fetch(`/api/audio/list?folder=${encodeURIComponent(audioFolder.value.trim())}`)
    if (!r.ok) throw new Error((await r.json()).detail)
    const data = await r.json()
    audioFiles.value = data.files
  } catch (e) {
    globalError.value = e.message
    audioFiles.value = []
  } finally {
    audioLoading.value = false
  }
}

async function openFolderPicker() {
  browseLoading.value = true
  try {
    const r = await fetch('/api/browse/folder', { method: 'POST' })
    if (!r.ok) throw new Error((await r.json()).detail)
    const data = await r.json()
    if (data.path) {
      audioFolder.value = data.path
      await loadAudioList()
    }
  } catch (e) {
    globalError.value = e.message
  } finally {
    browseLoading.value = false
  }
}

// -----------------------------------------------------------------------
// Suno AI audio
// -----------------------------------------------------------------------

async function checkSunoAudio() {
  try {
    const r = await fetch(`/api/concepts/${id}/audio/info`)
    if (!r.ok) return
    const data = await r.json()
    if (data.exists) {
      sunoAudio.value = { path: data.path, name: data.name, size_kb: data.size_kb }
      audioTab.value  = 'suno'
    }
  } catch { /* ignore */ }
}

async function runSunoAudio() {
  sunoError.value   = ''
  globalError.value = ''
  const r = await fetch(`/api/concepts/${id}/run/audio`, { method: 'POST' })
  if (!r.ok) {
    const err = await r.json()
    sunoError.value = err.detail
    return
  }
  jobStage.value   = 'audio'
  jobRunning.value = true
  startPolling()
}

// -----------------------------------------------------------------------
// Pipeline triggers
// -----------------------------------------------------------------------

async function runImage() {
  globalError.value = ''
  const r = await fetch(`/api/concepts/${id}/run/image`, { method: 'POST' })
  if (!r.ok) { globalError.value = (await r.json()).detail; return }
  jobStage.value = 'image'; jobRunning.value = true
  startPolling()
}

async function runVideo() {
  globalError.value = ''
  const r = await fetch(`/api/concepts/${id}/run/video`, { method: 'POST' })
  if (!r.ok) { globalError.value = (await r.json()).detail; return }
  jobStage.value = 'video'; jobRunning.value = true
  startPolling()
}

async function runSeo() {
  globalError.value = ''
  const r = await fetch(`/api/concepts/${id}/run/seo`, { method: 'POST' })
  if (!r.ok) { globalError.value = (await r.json()).detail; return }
  jobStage.value = 'seo'; jobRunning.value = true
  startPolling()
}

async function runAssemble() {
  if (!effectiveAudioPath.value) return
  globalError.value = ''
  const r = await fetch(`/api/concepts/${id}/run/assemble`, {
    method:  'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      audio_path:     effectiveAudioPath.value,
      breathing_zoom: breathingZoom.value,
    }),
  })
  if (!r.ok) { globalError.value = (await r.json()).detail; return }
  jobStage.value = 'assemble'; jobRunning.value = true
  startPolling()
}

async function uploadToYouTube() {
  uploading.value = true
  globalError.value = ''
  try {
    const r = await fetch(`/api/concepts/${id}/upload`, { method: 'POST' })
    if (!r.ok) throw new Error((await r.json()).detail)
    jobStage.value = 'upload'; jobRunning.value = true
    startPolling()
  } catch (e) {
    globalError.value = e.message
  } finally {
    uploading.value = false
  }
}

// -----------------------------------------------------------------------
// SEO editing
// -----------------------------------------------------------------------

async function saveField(field, value) {
  await fetch(`/api/concepts/${id}/metadata`, {
    method:  'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ field, value }),
  })
}

function addHashtag() {
  const tag = newTag.value.trim()
  if (!tag) return
  const h = tag.startsWith('#') ? tag : `#${tag}`
  meta.value.hashtags.push(h)
  meta.value.tags.push(h.slice(1))
  saveField('hashtags', meta.value.hashtags)
  saveField('tags', meta.value.tags)
  newTag.value = ''
}

function removeHashtag(i) {
  meta.value.hashtags.splice(i, 1)
  meta.value.tags.splice(i, 1)
  saveField('hashtags', meta.value.hashtags)
  saveField('tags', meta.value.tags)
}

// -----------------------------------------------------------------------
// Lifecycle
// -----------------------------------------------------------------------

onMounted(async () => {
  await load()
  await loadMeta()
  await checkSunoAudio()
  startPolling()
})

onUnmounted(() => {
  clearInterval(pollTimer)
})
</script>
