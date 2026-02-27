import { createApp } from 'vue'
import { createRouter, createWebHistory } from 'vue-router'
import App from './App.vue'
import './style.css'

// Views
import ConceptsView   from './components/ConceptsView.vue'
import ReviewView     from './components/ReviewView.vue'
import HistoryView    from './components/HistoryView.vue'
import ProjectsView   from './components/ProjectsView.vue'
import ProjectView    from './components/ProjectView.vue'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/',               redirect: '/projects'      },
    { path: '/projects',       component: ProjectsView,   name: 'projects' },
    { path: '/project/:id',    component: ProjectView,    name: 'project'  },
    { path: '/concepts',       component: ConceptsView,   name: 'concepts' },
    { path: '/review/:id',     component: ReviewView,     name: 'review'   },
    { path: '/history',        component: HistoryView,    name: 'history'  },
  ],
})

createApp(App).use(router).mount('#app')
