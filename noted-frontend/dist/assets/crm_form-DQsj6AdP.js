import{a as c,o as S,c as E,r as o}from"./main-CO7qj62s.js";class F{async generateForm(s){return c.post(`/sessions/${s}/crm-form`)}async getForm(s){return c.get(`/sessions/${s}/crm-form`)}async saveForm(s,l){return c.put(`/sessions/${s}/crm-form`,l)}}const u=new F,A={name:"CRMForm",props:{sessionId:{type:String,default:null}},setup(i){const s=o(!0),l=o(!1),e=o(null),r=o(null),d=o(""),m=o({}),v=["in-person","phone","video","email"],p=["resolved","follow-up needed","referred","pending","cancelled"],b=["encounter_type","advisor_name","client_name","outcome"],f=E(()=>{var t;return((t=e.value)==null?void 0:t.status)==="submitted"}),g=()=>{const t={};return e.value?(b.forEach(a=>{const n=e.value[a];(!n||typeof n=="string"&&n.trim()==="")&&(t[a]=`${a.replace(/_/g," ")} is required`)}),m.value=t,Object.keys(t).length===0):!1},x=async()=>{if(i.sessionId){s.value=!0,r.value=null;try{e.value=await u.getForm(i.sessionId)}catch(t){if(t.status===404)try{e.value=await u.generateForm(i.sessionId)}catch{r.value="Failed to generate CRM form. Make sure the session has a summary."}else r.value="Failed to load CRM form."}finally{s.value=!1}}},y=async(t=!1)=>{if(e.value){if(t&&!g()){r.value="Please fill in all required fields before submitting.",setTimeout(()=>{r.value=null},4e3);return}l.value=!0,r.value=null,d.value="";try{const a={...e.value};t&&(a.status="submitted"),e.value=await u.saveForm(i.sessionId,a),d.value=t?"Form submitted successfully!":"Draft saved.",setTimeout(()=>{d.value=""},3e3)}catch{r.value="Failed to save form."}finally{l.value=!1}}},h=()=>{e.value.action_items||(e.value.action_items=[]),e.value.action_items.push("")},w=t=>{e.value.action_items.splice(t,1)},k=()=>{e.value.referrals||(e.value.referrals=[]),e.value.referrals.push("")},D=t=>{e.value.referrals.splice(t,1)},_=()=>{window.history.back()};return S(()=>{x()}),{loading:s,saving:l,formData:e,error:r,successMessage:d,validationErrors:m,encounterTypes:v,outcomeOptions:p,isSubmitted:f,saveForm:y,addActionItem:h,removeActionItem:w,addReferral:k,removeReferral:D,goBack:_,requiredFields:b}},template:`
        <div class="min-h-screen bg-gray-50">
            <header class="bg-white border-b border-gray-200 px-6 py-4">
                <div class="flex items-center justify-between">
                    <div class="flex items-center space-x-4">
                        <button @click="goBack" class="flex items-center space-x-2 text-gray-600 hover:text-gray-900">
                            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 19l-7-7 7-7"/>
                            </svg>
                            <span>Back</span>
                        </button>
                        <h1 class="text-xl font-semibold text-gray-900">CRM Encounter Form</h1>
                    </div>
                    <div v-if="formData" class="flex items-center space-x-3">
                        <span v-if="isSubmitted" class="px-3 py-1 text-xs font-medium bg-green-100 text-green-800 rounded-full">Submitted</span>
                        <span v-else class="px-3 py-1 text-xs font-medium bg-yellow-100 text-yellow-800 rounded-full">Draft</span>
                    </div>
                </div>
            </header>

            <main class="max-w-3xl mx-auto px-6 py-8">
                <!-- Loading -->
                <div v-if="loading" class="text-center py-16 text-gray-500">Loading form...</div>

                <!-- Error -->
                <div v-else-if="error && !formData" class="text-center py-16">
                    <p class="text-red-600 mb-4">{{ error }}</p>
                    <button @click="goBack" class="px-4 py-2 bg-gray-200 rounded-md text-sm">Go Back</button>
                </div>

                <!-- Form -->
                <div v-else-if="formData" class="space-y-8">
                    <!-- Success/Error banners -->
                    <div v-if="successMessage" class="p-3 bg-green-50 border border-green-200 rounded-md text-sm text-green-800">{{ successMessage }}</div>
                    <div v-if="error" class="p-3 bg-red-50 border border-red-200 rounded-md text-sm text-red-800">{{ error }}</div>

                    <!-- Encounter Details -->
                    <section class="bg-white rounded-lg border border-gray-200 p-6 space-y-4">
                        <h2 class="text-lg font-medium text-gray-900 border-b border-gray-200 pb-2">Encounter Details</h2>

                        <div class="grid grid-cols-2 gap-4">
                            <div>
                                <label class="block text-sm font-medium text-gray-700 mb-1">
                                    Encounter Type <span class="text-red-500">*</span>
                                </label>
                                <select v-model="formData.encounter_type" :disabled="isSubmitted"
                                    :class="{'border-red-500': validationErrors.encounter_type}"
                                    class="w-full px-3 py-2 border border-gray-300 rounded-md text-sm focus:ring-2 focus:ring-blue-500 disabled:bg-gray-100">
                                    <option value="">— Select —</option>
                                    <option v-for="t in encounterTypes" :key="t" :value="t">{{ t }}</option>
                                </select>
                                <p v-if="validationErrors.encounter_type" class="text-xs text-red-500 mt-1">{{ validationErrors.encounter_type }}</p>
                            </div>
                            <div>
                                <label class="block text-sm font-medium text-gray-700 mb-1">Encounter Date</label>
                                <input type="date" :value="formData.encounter_date?.split('T')[0]" @input="formData.encounter_date = $event.target.value" :disabled="isSubmitted" class="w-full px-3 py-2 border border-gray-300 rounded-md text-sm focus:ring-2 focus:ring-blue-500 disabled:bg-gray-100"/>
                            </div>
                            <div>
                                <label class="block text-sm font-medium text-gray-700 mb-1">
                                    Advisor Name <span class="text-red-500">*</span>
                                </label>
                                <input v-model="formData.advisor_name" :disabled="isSubmitted"
                                    :class="{'border-red-500': validationErrors.advisor_name}"
                                    class="w-full px-3 py-2 border border-gray-300 rounded-md text-sm focus:ring-2 focus:ring-blue-500 disabled:bg-gray-100" placeholder="Advisor name"/>
                                <p v-if="validationErrors.advisor_name" class="text-xs text-red-500 mt-1">{{ validationErrors.advisor_name }}</p>
                            </div>
                            <div>
                                <label class="block text-sm font-medium text-gray-700 mb-1">
                                    Client Name <span class="text-red-500">*</span>
                                </label>
                                <input v-model="formData.client_name" :disabled="isSubmitted"
                                    :class="{'border-red-500': validationErrors.client_name}"
                                    class="w-full px-3 py-2 border border-gray-300 rounded-md text-sm focus:ring-2 focus:ring-blue-500 disabled:bg-gray-100" placeholder="Client name"/>
                                <p v-if="validationErrors.client_name" class="text-xs text-red-500 mt-1">{{ validationErrors.client_name }}</p>
                            </div>
                            <div>
                                <label class="block text-sm font-medium text-gray-700 mb-1">Client ID</label>
                                <input v-model="formData.client_id" :disabled="isSubmitted" class="w-full px-3 py-2 border border-gray-300 rounded-md text-sm focus:ring-2 focus:ring-blue-500 disabled:bg-gray-100" placeholder="Client ID"/>
                            </div>
                            <div>
                                <label class="block text-sm font-medium text-gray-700 mb-1">
                                    Outcome <span class="text-red-500">*</span>
                                </label>
                                <select v-model="formData.outcome" :disabled="isSubmitted"
                                    :class="{'border-red-500': validationErrors.outcome}"
                                    class="w-full px-3 py-2 border border-gray-300 rounded-md text-sm focus:ring-2 focus:ring-blue-500 disabled:bg-gray-100">
                                    <option value="">— Select —</option>
                                    <option v-for="o in outcomeOptions" :key="o" :value="o">{{ o }}</option>
                                </select>
                                <p v-if="validationErrors.outcome" class="text-xs text-red-500 mt-1">{{ validationErrors.outcome }}</p>
                            </div>
                        </div>
                    </section>

                    <!-- Topics Discussed (auto-filled) -->
                    <section class="bg-white rounded-lg border border-gray-200 p-6 space-y-3">
                        <h2 class="text-lg font-medium text-gray-900 border-b border-gray-200 pb-2">Topics Discussed</h2>
                        <div v-if="formData.topics_discussed && formData.topics_discussed.length">
                            <div v-for="(topic, i) in formData.topics_discussed" :key="i" class="flex items-center space-x-2 py-1">
                                <span class="px-2 py-1 text-xs bg-blue-100 text-blue-800 rounded">{{ typeof topic === 'string' ? topic : (topic.topic || 'Topic ' + (i+1)) }}</span>
                            </div>
                        </div>
                        <p v-else class="text-sm text-gray-400 italic">No topics auto-detected.</p>
                    </section>

                    <!-- Action Items -->
                    <section class="bg-white rounded-lg border border-gray-200 p-6 space-y-3">
                        <div class="flex items-center justify-between border-b border-gray-200 pb-2">
                            <h2 class="text-lg font-medium text-gray-900">Action Items</h2>
                            <button v-if="!isSubmitted" @click="addActionItem" class="text-sm text-blue-600 hover:text-blue-800">+ Add</button>
                        </div>
                        <div v-if="formData.action_items && formData.action_items.length" class="space-y-2">
                            <div v-for="(item, i) in formData.action_items" :key="i" class="flex items-center space-x-2">
                                <input v-model="formData.action_items[i]" :disabled="isSubmitted" class="flex-1 px-3 py-2 border border-gray-300 rounded-md text-sm focus:ring-2 focus:ring-blue-500 disabled:bg-gray-100" :placeholder="'Action item ' + (i+1)"/>
                                <button v-if="!isSubmitted" @click="removeActionItem(i)" class="text-red-400 hover:text-red-600">
                                    <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"/></svg>
                                </button>
                            </div>
                        </div>
                        <p v-else class="text-sm text-gray-400 italic">No action items.</p>
                    </section>

                    <!-- Follow-up -->
                    <section class="bg-white rounded-lg border border-gray-200 p-6 space-y-4">
                        <h2 class="text-lg font-medium text-gray-900 border-b border-gray-200 pb-2">Follow-up</h2>
                        <div class="grid grid-cols-2 gap-4">
                            <div>
                                <label class="block text-sm font-medium text-gray-700 mb-1">Follow-up Date</label>
                                <input type="date" :value="formData.follow_up_date?.split('T')[0]" @input="formData.follow_up_date = $event.target.value" :disabled="isSubmitted" class="w-full px-3 py-2 border border-gray-300 rounded-md text-sm focus:ring-2 focus:ring-blue-500 disabled:bg-gray-100"/>
                            </div>
                        </div>
                        <div>
                            <label class="block text-sm font-medium text-gray-700 mb-1">Follow-up Notes</label>
                            <textarea v-model="formData.follow_up_notes" :disabled="isSubmitted" rows="3" class="w-full px-3 py-2 border border-gray-300 rounded-md text-sm focus:ring-2 focus:ring-blue-500 disabled:bg-gray-100" placeholder="Notes for follow-up..."></textarea>
                        </div>
                    </section>

                    <!-- Referrals -->
                    <section class="bg-white rounded-lg border border-gray-200 p-6 space-y-3">
                        <div class="flex items-center justify-between border-b border-gray-200 pb-2">
                            <h2 class="text-lg font-medium text-gray-900">Referrals</h2>
                            <button v-if="!isSubmitted" @click="addReferral" class="text-sm text-blue-600 hover:text-blue-800">+ Add</button>
                        </div>
                        <div v-if="formData.referrals && formData.referrals.length" class="space-y-2">
                            <div v-for="(ref, i) in formData.referrals" :key="i" class="flex items-center space-x-2">
                                <input v-model="formData.referrals[i]" :disabled="isSubmitted" class="flex-1 px-3 py-2 border border-gray-300 rounded-md text-sm focus:ring-2 focus:ring-blue-500 disabled:bg-gray-100" :placeholder="'Service / department'"/>
                                <button v-if="!isSubmitted" @click="removeReferral(i)" class="text-red-400 hover:text-red-600">
                                    <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"/></svg>
                                </button>
                            </div>
                        </div>
                        <p v-else class="text-sm text-gray-400 italic">No referrals added.</p>
                    </section>

                    <!-- Notes -->
                    <section class="bg-white rounded-lg border border-gray-200 p-6 space-y-3">
                        <h2 class="text-lg font-medium text-gray-900 border-b border-gray-200 pb-2">Additional Notes</h2>
                        <textarea v-model="formData.notes" :disabled="isSubmitted" rows="4" class="w-full px-3 py-2 border border-gray-300 rounded-md text-sm focus:ring-2 focus:ring-blue-500 disabled:bg-gray-100" placeholder="Any additional notes..."></textarea>
                    </section>

                    <!-- Actions -->
                    <div v-if="!isSubmitted" class="flex items-center justify-end space-x-3 pb-8">
                        <button @click="saveForm(false)" :disabled="saving" class="px-4 py-2 border border-gray-300 text-gray-700 text-sm font-medium rounded-md hover:bg-gray-50 disabled:opacity-50">
                            {{ saving ? 'Saving...' : 'Save Draft' }}
                        </button>
                        <button @click="saveForm(true)" :disabled="saving || (Object.keys(validationErrors).length > 0)" class="px-4 py-2 bg-black text-white text-sm font-medium rounded-md hover:bg-gray-800 disabled:opacity-50">
                            {{ saving ? 'Submitting...' : 'Submit Form' }}
                        </button>
                    </div>
                </div>
            </main>
        </div>
    `};export{A as default};
