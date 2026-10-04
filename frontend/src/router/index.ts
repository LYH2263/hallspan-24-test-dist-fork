import { createRouter, createWebHistory } from 'vue-router'

const routes = [
  { path: '/halls', name: 'Halls', component: () => import('../views/Halls.vue') },
  { path: '/candidates', name: 'Candidates', component: () => import('../views/Candidates.vue') },
  { path: '/papers', name: 'Papers', component: () => import('../views/Papers.vue') },
  { path: '/map', name: 'Map', component: () => import('../views/Map.vue') },
  { path: '/violations', name: 'Violations', component: () => import('../views/Violations.vue') },
  { path: '/stats', name: 'Stats', component: () => import('../views/Stats.vue') },
  { path: '/', redirect: '/halls' },
]

export default createRouter({
  history: createWebHistory(),
  routes,
})
