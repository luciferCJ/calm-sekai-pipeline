<template>
  <div class="p-8 max-w-6xl mx-auto animate-fade-in">
    <!-- Header -->
    <div class="flex items-center justify-between mb-8">
      <div>
        <h1 class="text-xl font-semibold text-sekai-text">Concepts</h1>
        <p class="text-sm text-sekai-subtle mt-1">Generate and approve video concepts</p>
      </div>
      <button class="btn-primary flex items-center gap-2" :disabled="generating" @click="generateConcept">
        <span v-if="generating" class="w-3.5 h-3.5 border-2 border-sekai-bg border-t-transparent rounded-full animate-spin" />
        {{ generating ? 'Generating…' : '+ New Concept' }}
      </button>
    </div>

    <!-- Generate options (collapsible) -->
    <div v-if="showOptions" class="card mb-3">
      <p class="label mb-4">Override generation parameters (optional)</p>
      <div class="grid grid-cols-3 gap-4">
        <div>
          <p class="label mb-1.5">Theme</p>
          <select v-model="opts.theme" class="input">
            <option value="">Auto</option>
            <option v-for="t in themes" :key="t" :value="t">{{ t }}</option>
          </select>
        </div>
        <div>
          <p class="label mb-1.5">Emotion</p>
          <select v-model="opts.emotion" class="input">
            <option value="">Auto</option>
            <option v-for="e in emotions" :key="e" :value="e">{{ e }}</option>
          </select>
        </div>
        <div>
          <p class="label mb-1.5">Format</p>
          <select v-model="opts.format_" class="input">
            <option value="">Auto</option>
            <option value="shorts_10s">10s Short</option>
            <option value="shorts_30s">30s Short</option>
          </select>
        </div>
      </div>
    </div>
    <button
      class="text-xs text-sekai-subtle hover:text-sekai-text mb-2 transition-colors block"
      @click="showOptions = !showOptions"
    >
      {{ showOptions ? '▲ Hide options' : '▼ Set theme / emotion / format' }}
    </button>

    <!-- System prompt editor (collapsible) -->
    <div v-if="showPrompt" class="card mb-3">
      <div class="flex items-center justify-between mb-3">
        <p class="label">Generation Prompt (GPT-4o system prompt)</p>
        <span v-if="promptMsg" class="text-xs text-sekai-accent">{{ promptMsg }}</span>
      </div>
      <textarea
        v-model="promptText"
        class="textarea text-xs font-mono"
        rows="14"
      />
      <div class="flex gap-2 mt-3">
        <button class="btn-primary text-xs" @click="savePrompt">Save</button>
        <button class="btn-ghost text-xs" @click="resetPrompt">Reset to default</button>
      </div>
    </div>
    <button
      class="text-xs text-sekai-subtle hover:text-sekai-text mb-6 transition-colors block"
      @click="togglePromptEditor"
    >
      {{ showPrompt ? '▲ Hide prompt editor' : '⚙ Edit generation prompt' }}
    </button>

    <!-- Error banner -->
    <div v-if="error" class="bg-sekai-error/10 border border-sekai-error/30 text-sekai-error text-sm rounded-lg px-4 py-3 mb-6">
      {{ error }}
    </div>

    <!-- Loading -->
    <div v-if="loading" class="text-sekai-subtle text-sm">Loading concepts…</div>

    <!-- Empty state -->
    <div v-else-if="!concepts.length" class="text-center py-20 text-sekai-subtle">
      <p class="text-4xl mb-4">✦</p>
      <p class="text-sm">No concepts yet. Generate your first one.</p>
    </div>

    <!-- Concept cards -->
    <div v-else class="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
      <ConceptCard
        v-for="c in concepts"
        :key="c.id"
        :concept="c"
        @approve="approve(c.id)"
        @reject="reject(c.id)"
        @review="$router.push(`/review/${c.id}`)"
        @refresh="load"
      />
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import ConceptCard from './ConceptCard.vue'

const concepts    = ref([])
const loading     = ref(true)
const generating  = ref(false)
const error       = ref('')
const showOptions = ref(false)
const opts = ref({ theme: '', emotion: '', format_: '' })

// System prompt editor
const showPrompt = ref(false)
const promptText = ref('')
const promptMsg  = ref('')

const themes = [
  'Fairy / Forest Spirits', 'Sakura / Seasons', 'Lost Spirits / Wandering Souls',
  'Cozy Interiors / Rainy Windows', 'Ocean / Water Spirits', 'Night Sky / Moonlit Scenes',
]
const emotions = ['longing', 'healing', 'quiet magic', 'melancholic peace', 'soft wonder', 'gentle nostalgia']

async function load() {
  try {
    const r = await fetch('/api/concepts')
    concepts.value = await r.json()
  } catch (e) {
    error.value = 'Could not load concepts.'
  } finally {
    loading.value = false
  }
}

async function generateConcept() {
  error.value = ''
  generating.value = true
  try {
    const body = {}
    if (opts.value.theme)   body.theme   = opts.value.theme
    if (opts.value.emotion) body.emotion  = opts.value.emotion
    if (opts.value.format_) body.format_  = opts.value.format_

    const r = await fetch('/api/concepts/generate', {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify(body),
    })
    if (!r.ok) throw new Error((await r.json()).detail)
    await load()
  } catch (e) {
    error.value = e.message
  } finally {
    generating.value = false
  }
}

async function approve(id) {
  await fetch(`/api/concepts/${id}/approve`, { method: 'POST' })
  await load()
}

async function reject(id) {
  await fetch(`/api/concepts/${id}/reject`, { method: 'POST' })
  await load()
}

// -----------------------------------------------------------------------
// Prompt editor
// -----------------------------------------------------------------------

async function togglePromptEditor() {
  showPrompt.value = !showPrompt.value
  if (showPrompt.value && !promptText.value) {
    const r = await fetch('/api/prompts/concept')
    const d = await r.json()
    promptText.value = d.prompt
  }
}

async function savePrompt() {
  promptMsg.value = ''
  try {
    const r = await fetch('/api/prompts/concept', {
      method:  'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify({ prompt: promptText.value }),
    })
    if (!r.ok) throw new Error((await r.json()).detail)
    promptMsg.value = 'Saved ✓'
    setTimeout(() => { promptMsg.value = '' }, 2000)
  } catch (e) {
    promptMsg.value = `Error: ${e.message}`
  }
}

async function resetPrompt() {
  try {
    await fetch('/api/prompts/concept', {
      method:  'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify({ prompt: '' }),
    })
    // Reload the default
    const r = await fetch('/api/prompts/concept')
    const d = await r.json()
    promptText.value = d.prompt
    promptMsg.value  = 'Reset to default ✓'
    setTimeout(() => { promptMsg.value = '' }, 2000)
  } catch (e) {
    promptMsg.value = `Error: ${e.message}`
  }
}

onMounted(load)
</script>
