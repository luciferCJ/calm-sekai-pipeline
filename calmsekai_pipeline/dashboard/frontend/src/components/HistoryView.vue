<template>
  <div class="p-8 max-w-4xl mx-auto animate-fade-in">
    <div class="mb-8">
      <h1 class="text-xl font-semibold">History</h1>
      <p class="text-sm text-sekai-subtle mt-1">All uploaded and completed concepts</p>
    </div>

    <div v-if="loading" class="text-sekai-subtle text-sm">Loading…</div>

    <div v-else-if="!concepts.length" class="text-center py-20 text-sekai-subtle">
      <p class="text-4xl mb-4">✦</p>
      <p class="text-sm">No completed concepts yet.</p>
    </div>

    <div v-else class="space-y-3">
      <div
        v-for="c in concepts"
        :key="c.id"
        class="card flex items-center gap-4 cursor-pointer hover:border-sekai-accent/40 transition-colors"
        @click="$router.push(`/review/${c.id}`)"
      >
        <!-- Thumbnail -->
        <div class="w-12 h-20 rounded-lg overflow-hidden bg-sekai-surface shrink-0">
          <img
            v-if="hasImage(c)"
            :src="`/api/concepts/${c.id}/image`"
            class="w-full h-full object-cover"
          />
          <div v-else class="w-full h-full flex items-center justify-center text-sekai-muted text-xs">
            —
          </div>
        </div>

        <!-- Info -->
        <div class="flex-1 min-w-0">
          <p class="text-sm font-medium text-sekai-text truncate">{{ c.theme }}</p>
          <p class="text-xs text-sekai-subtle mt-0.5">{{ c.emotion }}</p>
          <p class="text-xs text-sekai-muted mt-1">{{ fmtDate(c.created_at) }}</p>
        </div>

        <!-- Status -->
        <StatusBadge :status="c.status" />

        <span class="text-sekai-subtle text-sm">→</span>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import StatusBadge from './StatusBadge.vue'

const concepts = ref([])
const loading  = ref(true)

const DONE_STATUSES = ['assembly_done', 'seo_done', 'uploaded']

function hasImage(c) {
  return !['pending_approval', 'approved', 'rejected'].includes(c.status)
}

function fmtDate(iso) {
  if (!iso) return ''
  return new Date(iso).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })
}

async function load() {
  try {
    const r = await fetch('/api/concepts')
    const all = await r.json()
    concepts.value = all.filter(c => DONE_STATUSES.includes(c.status))
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>
