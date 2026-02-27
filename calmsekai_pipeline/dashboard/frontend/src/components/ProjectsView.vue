<template>
  <div class="p-8 max-w-6xl mx-auto animate-fade-in">
    <!-- Header -->
    <div class="flex items-center justify-between mb-8">
      <div>
        <h1 class="text-xl font-semibold text-sekai-text">Projects</h1>
        <p class="text-sm text-sekai-subtle mt-1">Multi-scene video stories</p>
      </div>
      <button class="btn-primary flex items-center gap-2" @click="showModal = true">
        + New Project
      </button>
    </div>

    <!-- Error banner -->
    <div v-if="error" class="bg-sekai-error/10 border border-sekai-error/30 text-sekai-error text-sm rounded-lg px-4 py-3 mb-6">
      {{ error }}
    </div>

    <!-- Loading -->
    <div v-if="loading" class="text-sekai-subtle text-sm">Loading projects…</div>

    <!-- Empty state -->
    <div v-else-if="!projects.length" class="text-center py-20 text-sekai-subtle">
      <p class="text-4xl mb-4">✦</p>
      <p class="text-sm">No projects yet. Create your first story.</p>
    </div>

    <!-- Project cards -->
    <div v-else class="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
      <div
        v-for="p in projects"
        :key="p.id"
        class="card flex flex-col gap-3 cursor-pointer hover:border-sekai-accent/40 transition-colors animate-fade-in"
        @click="$router.push(`/project/${p.id}`)"
      >
        <div class="flex items-start justify-between gap-2">
          <div class="flex-1 min-w-0">
            <p class="text-sm font-medium text-sekai-text truncate">{{ p.title }}</p>
            <p class="text-xs text-sekai-subtle mt-0.5">{{ p.theme }} · {{ p.emotion }}</p>
          </div>
          <StatusBadge :status="p.status" />
        </div>
        <div class="flex gap-2 flex-wrap">
          <span class="text-xs px-2 py-0.5 rounded-full bg-sekai-muted/30 text-sekai-subtle">
            {{ p.aspect_ratio }}
          </span>
          <span class="text-xs px-2 py-0.5 rounded-full bg-sekai-muted/30 text-sekai-subtle">
            {{ p.target_duration }}s
          </span>
          <span class="text-xs px-2 py-0.5 rounded-full bg-sekai-muted/30 text-sekai-subtle">
            {{ (p.scene_ids || []).length }} scenes
          </span>
          <span class="text-xs px-2 py-0.5 rounded-full bg-sekai-muted/30 text-sekai-subtle">
            {{ timeAgo(p.created_at) }}
          </span>
        </div>
        <p v-if="p.audio_mood" class="text-xs text-sekai-subtle italic truncate">"{{ p.audio_mood }}"</p>
      </div>
    </div>

    <!-- Create project modal -->
    <Teleport to="body">
      <div
        v-if="showModal"
        class="fixed inset-0 bg-black/60 flex items-center justify-center z-50 p-4"
        @click.self="closeModal"
      >
        <div class="card w-full max-w-lg animate-fade-in" @click.stop>
          <div class="flex items-center justify-between mb-6">
            <h2 class="text-base font-semibold text-sekai-text">New Project</h2>
            <button class="text-sekai-subtle hover:text-sekai-text text-xl leading-none" @click="closeModal">×</button>
          </div>

          <!-- Title -->
          <div class="mb-4">
            <p class="label mb-1.5">Story Title</p>
            <input
              v-model="form.title"
              class="input w-full"
              placeholder="e.g. The Last Lantern Spirit"
            />
          </div>

          <!-- Theme + Emotion -->
          <div class="grid grid-cols-2 gap-4 mb-4">
            <div>
              <p class="label mb-1.5">Theme</p>
              <select v-model="form.theme" class="input">
                <option v-for="t in themes" :key="t" :value="t">{{ t }}</option>
              </select>
            </div>
            <div>
              <p class="label mb-1.5">Emotion</p>
              <select v-model="form.emotion" class="input">
                <option v-for="e in emotions" :key="e" :value="e">{{ e }}</option>
              </select>
            </div>
          </div>

          <!-- Aspect ratio -->
          <div class="mb-4">
            <p class="label mb-1.5">Aspect Ratio</p>
            <div class="flex gap-2">
              <button
                v-for="ar in aspectRatios"
                :key="ar.value"
                class="flex-1 py-2 rounded-lg text-xs font-medium border transition-colors"
                :class="form.aspect_ratio === ar.value
                  ? 'border-sekai-accent bg-sekai-accent/10 text-sekai-accent'
                  : 'border-sekai-border text-sekai-subtle hover:text-sekai-text'"
                @click="form.aspect_ratio = ar.value"
              >
                {{ ar.label }}
              </button>
            </div>
          </div>

          <!-- Target duration -->
          <div class="mb-6">
            <p class="label mb-1.5">Target Duration</p>
            <div class="flex gap-2 flex-wrap">
              <button
                v-for="d in durations"
                :key="d.value"
                class="py-2 px-3 rounded-lg text-xs font-medium border transition-colors"
                :class="form.target_duration === d.value
                  ? 'border-sekai-accent bg-sekai-accent/10 text-sekai-accent'
                  : 'border-sekai-border text-sekai-subtle hover:text-sekai-text'"
                @click="form.target_duration = d.value"
              >
                {{ d.label }}
              </button>
              <input
                v-model.number="form.target_duration"
                type="number"
                min="10"
                max="600"
                class="input w-24 text-xs py-1.5"
                placeholder="custom"
              />
            </div>
          </div>

          <!-- Actions -->
          <div class="flex gap-2">
            <button
              class="btn-primary flex-1 flex items-center justify-center gap-2"
              :disabled="generating || !form.title.trim()"
              @click="createProject"
            >
              <span v-if="generating" class="w-3.5 h-3.5 border-2 border-sekai-bg border-t-transparent rounded-full animate-spin" />
              {{ generating ? 'Generating…' : 'Generate Project' }}
            </button>
            <button class="btn-ghost" @click="closeModal">Cancel</button>
          </div>

          <div v-if="modalError" class="mt-3 text-xs text-sekai-error">{{ modalError }}</div>
        </div>
      </div>
    </Teleport>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import StatusBadge from './StatusBadge.vue'

const router     = useRouter()
const projects   = ref([])
const loading    = ref(true)
const error      = ref('')
const showModal  = ref(false)
const generating = ref(false)
const modalError = ref('')

const themes = [
  'Fairy / Forest Spirits', 'Sakura / Seasons', 'Lost Spirits / Wandering Souls',
  'Cozy Interiors / Rainy Windows', 'Ocean / Water Spirits', 'Night Sky / Moonlit Scenes',
]
const emotions = ['longing', 'healing', 'quiet magic', 'melancholic peace', 'soft wonder', 'gentle nostalgia']

const aspectRatios = [
  { value: '9:16', label: '9:16 Portrait' },
  { value: '16:9', label: '16:9 Landscape' },
  { value: '1:1',  label: '1:1 Square' },
]

const durations = [
  { value: 30,  label: '30s' },
  { value: 60,  label: '60s' },
  { value: 180, label: '3min' },
]

const defaultForm = () => ({
  title:           '',
  theme:           themes[0],
  emotion:         emotions[0],
  aspect_ratio:    '9:16',
  target_duration: 30,
})

const form = ref(defaultForm())

async function load() {
  try {
    const r = await fetch('/api/projects')
    projects.value = await r.json()
  } catch {
    error.value = 'Could not load projects.'
  } finally {
    loading.value = false
  }
}

async function createProject() {
  modalError.value = ''
  if (!form.value.title.trim()) return
  generating.value = true
  try {
    const r = await fetch('/api/projects/generate', {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify(form.value),
    })
    if (!r.ok) throw new Error((await r.json()).detail)
    const project = await r.json()
    closeModal()
    router.push(`/project/${project.id}`)
  } catch (e) {
    modalError.value = e.message
  } finally {
    generating.value = false
  }
}

function closeModal() {
  showModal.value  = false
  modalError.value = ''
  form.value       = defaultForm()
}

function timeAgo(iso) {
  if (!iso) return ''
  const diff = Date.now() - new Date(iso).getTime()
  const mins = Math.floor(diff / 60000)
  if (mins < 1)  return 'just now'
  if (mins < 60) return `${mins}m ago`
  const hrs = Math.floor(mins / 60)
  if (hrs < 24)  return `${hrs}h ago`
  return `${Math.floor(hrs / 24)}d ago`
}

onMounted(load)
</script>
