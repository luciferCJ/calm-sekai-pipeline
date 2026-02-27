<template>
  <div class="flex flex-col h-full">
    <!-- Top nav -->
    <nav class="flex items-center gap-8 px-8 py-4 border-b border-sekai-border shrink-0">
      <span class="text-sekai-glow font-semibold tracking-wide text-sm">CalmSekai</span>
      <div class="flex gap-1">
        <RouterLink
          v-for="link in nav"
          :key="link.to"
          :to="link.to"
          class="px-3 py-1.5 rounded-lg text-sm transition-colors"
          :class="$route.path.startsWith(link.to)
            ? 'text-sekai-accent bg-sekai-accent/10'
            : 'text-sekai-subtle hover:text-sekai-text'"
        >
          {{ link.label }}
        </RouterLink>
      </div>
    </nav>

    <!-- Page content -->
    <main class="flex-1 overflow-auto">
      <RouterView />
    </main>
  </div>
</template>

<script setup>
const nav = [
  { to: '/projects', label: 'Projects' },
  { to: '/concepts', label: 'Concepts' },
  { to: '/history',  label: 'History'  },
]
</script>
