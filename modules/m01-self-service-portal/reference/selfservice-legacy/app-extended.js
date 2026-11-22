// ========== ALB Functions ==========

async function loadALBs() {
    const contentEl = document.getElementById('alb-content');
    contentEl.innerHTML = '<div class="loading">Loading load balancers...</div>';
    
    try {
        const response = await fetch(`${API_BASE_URL}/alb/load-balancers`);
        const data = await response.json();
        
        albData = data.loadBalancers || [];
        
        if (albData.length > 0) {
            displayALBs(albData);
        } else {
            contentEl.innerHTML = '<p style="text-align:center;color:#6b7280;">No load balancers found. Create one to get started!</p>';
        }
        
        updateMetrics();
    } catch (error) {
        contentEl.innerHTML = '<p style="text-align:center;color:#ef4444;">Error loading load balancers</p>';
        console.error('ALB Load Error:', error);
    }
}

function displayALBs(loadBalancers) {
    const contentEl = document.getElementById('alb-content');
    let html = '';
    
    loadBalancers.forEach(lb => {
        const statusClass = lb.state === 'active' ? 'status-active' : 'status-inactive';
        const typeIcon = lb.type === 'application' ? '🌐' : '⚡';
        const typeLabel = lb.type === 'application' ? 'ALB' : 'NLB';
        
        html += `
            <div class="resource-card animated-card">
                <div class="resource-header">
                    <div style="display:flex;align-items:center;gap:10px;">
                        <span class="resource-icon">${typeIcon}</span>
                        <span class="resource-name">${lb.name}</span>
                    </div>
                    <span class="resource-status ${statusClass}">
                        ${lb.state.toUpperCase()}
                    </span>
                </div>
                <div class="resource-details">
                    <div><strong>Type:</strong> ${typeLabel} (${lb.type})</div>
                    <div><strong>DNS:</strong> ${lb.dnsName}</div>
                    <div><strong>Scheme:</strong> ${lb.scheme}</div>
                    <div><strong>Created:</strong> ${new Date(lb.createdTime).toLocaleString()}</div>
                </div>
            </div>
        `;
    });
    
    contentEl.innerHTML = html;
}

function createLoadBalancer(defaultType = 'application') {
    const typeLabel = defaultType === 'application' ? 'Application Load Balancer (ALB)' : 'Network Load Balancer (NLB)';
    const typeDescription = defaultType === 'application' 
        ? 'Best for HTTP/HTTPS traffic with advanced routing'
        : 'Best for TCP/UDP traffic with ultra-low latency';
    
    const modalBody = `
        ${ServiceDiagram.render('alb', { variant: defaultType === 'network' ? 'network' : 'application' })}
        <div class="info-box">
            <strong>${typeLabel}</strong>
            <p style="margin:5px 0 0 0;color:#6b7280;font-size:0.9em;">${typeDescription}</p>
        </div>
        <div class="form-group">
            <label>Load Balancer Name</label>
            <input type="text" id="lb-name" placeholder="my-load-balancer" />
        </div>
        <div class="form-group">
            <label>Subnets (comma-separated)</label>
            <input type="text" id="lb-subnets" placeholder="subnet-xxx,subnet-yyy" />
            <small style="color:#6b7280;">Minimum 2 subnets in different AZs</small>
        </div>
        <div class="form-group">
            <label>Scheme</label>
            <select id="lb-scheme">
                <option value="internet-facing">Internet-facing</option>
                <option value="internal">Internal</option>
            </select>
        </div>
        <div class="form-group">
            <label>Type</label>
            <select id="lb-type">
                <option value="application" ${defaultType === 'application' ? 'selected' : ''}>Application (ALB)</option>
                <option value="network" ${defaultType === 'network' ? 'selected' : ''}>Network (NLB)</option>
            </select>
        </div>
    `;
    
    showModal('Create Load Balancer', modalBody, async () => {
        const name = document.getElementById('lb-name').value.trim();
        const subnets = document.getElementById('lb-subnets').value.split(',').map(s => s.trim()).filter(Boolean);
        const scheme = document.getElementById('lb-scheme').value;
        const type = document.getElementById('lb-type').value;

        if (!name) {
            showToast('Load balancer name is required', 'error');
            return;
        }
        const subnetErr = FormValidation.validateSubnetIds(subnets);
        if (subnetErr && !subnetErr.startsWith('WARN:')) {
            showToast(subnetErr, 'error');
            return;
        }
        if (subnetErr && subnetErr.startsWith('WARN:')) {
            showToast(subnetErr.slice(6), 'info');
        }
        
        try {
            const response = await fetch(`${API_BASE_URL}/alb/load-balancers`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ name, subnets, scheme, type })
            });
            
            const result = await response.json();
            if (response.ok) {
                showToast('Load Balancer created successfully!', 'success');
                closeModal();
                refreshALB();
            } else {
                showToast(result.error || 'Failed to create load balancer', 'error');
            }
        } catch (error) {
            showToast('Error creating load balancer', 'error');
            console.error(error);
        }
    }, { size: 'xl' });
}

function refreshALB() {
    loadALBs();
}

// ========== S3 Functions ==========

async function loadS3Buckets() {
    const contentEl = document.getElementById('s3-content');
    contentEl.innerHTML = '<div class="loading">Loading S3 buckets...</div>';
    
    try {
        const response = await fetch(`${API_BASE_URL}/s3/buckets`);
        const data = await response.json();
        
        s3Data = data.buckets || [];
        
        if (s3Data.length > 0) {
            displayS3Buckets(s3Data);
        } else {
            contentEl.innerHTML = '<p style="text-align:center;color:#6b7280;">No S3 buckets found. Create one to get started!</p>';
        }
        
        updateMetrics();
    } catch (error) {
        contentEl.innerHTML = '<p style="text-align:center;color:#ef4444;">Error loading S3 buckets</p>';
        console.error('S3 Load Error:', error);
    }
}

function displayS3Buckets(buckets) {
    const contentEl = document.getElementById('s3-content');
    let html = '';
    
    buckets.forEach(bucket => {
        html += `
            <div class="resource-card animated-card">
                <div class="resource-header">
                    <div style="display:flex;align-items:center;gap:10px;">
                        <span class="resource-icon">🪣</span>
                        <span class="resource-name">${bucket.name}</span>
                    </div>
                    <span class="resource-status status-active">ACTIVE</span>
                </div>
                <div class="resource-details">
                    <div><strong>Region:</strong> ${bucket.region}</div>
                    <div><strong>Created:</strong> ${new Date(bucket.creationDate).toLocaleString()}</div>
                </div>
            </div>
        `;
    });
    
    contentEl.innerHTML = html;
}

function createS3Bucket() {
    const modalBody = `
        ${ServiceDiagram.render('s3')}
        <div class="info-box">
            <strong>🪣 S3 Bucket</strong>
            <p style="margin:5px 0 0 0;color:#6b7280;font-size:0.9em;">Store and retrieve any amount of data at any time</p>
        </div>
        <div class="form-group">
            <label>Bucket Name</label>
            <input type="text" id="bucket-name" placeholder="my-unique-bucket-name" />
            <small style="color:#6b7280;">Must be globally unique and DNS-compliant</small>
        </div>
        <div class="form-group">
            <label>
                <input type="checkbox" id="enable-website" />
                Enable Static Website Hosting
            </label>
        </div>
    `;
    
    showModal('Create S3 Bucket', modalBody, async () => {
        const bucketName = document.getElementById('bucket-name').value.trim().toLowerCase();
        const enableWebsite = document.getElementById('enable-website').checked;

        const err = FormValidation.validateS3Bucket(bucketName);
        if (err) {
            showToast(err, 'error');
            return;
        }
        
        try {
            const response = await fetch(`${API_BASE_URL}/s3/buckets`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ bucketName, enableWebsite })
            });
            
            const result = await response.json();
            if (response.ok) {
                showToast('S3 Bucket created successfully!', 'success');
                closeModal();
                refreshS3();
            } else {
                showToast(result.error || 'Failed to create bucket', 'error');
            }
        } catch (error) {
            showToast('Error creating bucket', 'error');
            console.error(error);
        }
    });
}

function createStaticWebsite() {
    const modalBody = `
        ${ServiceDiagram.render('static-website')}
        <div class="info-box">
            <strong>🌐 Static Website Hosting</strong>
            <p style="margin:5px 0 0 0;color:#6b7280;font-size:0.9em;">Host static HTML, CSS, and JavaScript files directly from S3</p>
        </div>
        <div class="form-group">
            <label>Website Bucket Name</label>
            <input type="text" id="website-bucket-name" placeholder="my-website-bucket" />
            <small style="color:#6b7280;">Will be configured with public read access and website hosting</small>
        </div>
    `;
    
    showModal('Create Static Website', modalBody, async () => {
        const bucketName = document.getElementById('website-bucket-name').value.trim().toLowerCase();

        const err = FormValidation.validateS3Bucket(bucketName);
        if (err) {
            showToast(err, 'error');
            return;
        }
        
        try {
            const response = await fetch(`${API_BASE_URL}/s3/buckets`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ bucketName, enableWebsite: true })
            });
            
            const result = await response.json();
            if (response.ok) {
                showToast('Static website bucket created!', 'success');
                closeModal();
                refreshS3();
            } else {
                showToast(result.error || 'Failed to create website', 'error');
            }
        } catch (error) {
            showToast('Error creating website', 'error');
            console.error(error);
        }
    });
}

function refreshS3() {
    loadS3Buckets();
}

// ========== ASG Functions ==========

async function loadASGs() {
    const contentEl = document.getElementById('asg-content');
    contentEl.innerHTML = '<div class="loading">Loading auto scaling groups...</div>';
    
    try {
        const response = await fetch(`${API_BASE_URL}/asg/groups`);
        const data = await response.json();
        
        asgData = data.autoScalingGroups || [];
        
        if (asgData.length > 0) {
            displayASGs(asgData);
        } else {
            contentEl.innerHTML = '<p style="text-align:center;color:#6b7280;">No auto scaling groups found. Create one to get started!</p>';
        }
        
        updateMetrics();
    } catch (error) {
        contentEl.innerHTML = '<p style="text-align:center;color:#ef4444;">Error loading auto scaling groups</p>';
        console.error('ASG Load Error:', error);
    }
}

function displayASGs(groups) {
    const contentEl = document.getElementById('asg-content');
    let html = '';
    
    groups.forEach(asg => {
        html += `
            <div class="resource-card animated-card">
                <div class="resource-header">
                    <div style="display:flex;align-items:center;gap:10px;">
                        <span class="resource-icon">📈</span>
                        <span class="resource-name">${asg.name}</span>
                    </div>
                    <span class="resource-status status-active">ACTIVE</span>
                </div>
                <div class="resource-details">
                    <div><strong>Capacity:</strong> ${asg.desiredCapacity} (Min: ${asg.minSize}, Max: ${asg.maxSize})</div>
                    <div><strong>Current Instances:</strong> ${asg.instanceCount}</div>
                    <div><strong>Health Check:</strong> ${asg.healthCheckType}</div>
                    <div><strong>Created:</strong> ${new Date(asg.createdTime).toLocaleString()}</div>
                </div>
            </div>
        `;
    });
    
    contentEl.innerHTML = html;
}

function createAutoScalingGroup() {
    const modalBody = `
        ${ServiceDiagram.render('asg')}
        <div class="alert alert-primary d-flex gap-3 align-items-start mb-4">
            <span class="fs-3">📈</span>
            <div>
                <strong>Create Auto Scaling Group</strong>
                <p class="mb-0 small text-muted">Automatically add or remove EC2 instances based on demand — keeps your app running smoothly</p>
            </div>
        </div>

        <div class="mb-4">
            <h6 class="text-primary fw-semibold mb-3">📛 Group Identity</h6>
            <label for="asg-name" class="form-label fw-medium">ASG Name <span class="text-danger">*</span></label>
            <input type="text" class="form-control" id="asg-name" placeholder="my-auto-scaling-group" maxlength="255">
            <div class="form-text">Unique name for this scaling group. Use lowercase letters, numbers, and hyphens (e.g. <code>prod-web-asg</code>)</div>
        </div>

        <div class="mb-4">
            <div class="d-flex justify-content-between align-items-center mb-3">
                <h6 class="text-primary fw-semibold mb-0">📋 Launch Template <span class="text-danger">*</span></h6>
                <button type="button" class="btn btn-sm btn-outline-primary" id="refresh-asg-templates">↻ Fetch Templates</button>
            </div>
            <div id="asg-template-loading" class="text-muted small mb-2">Loading launch templates...</div>
            <select class="form-select mb-2" id="asg-template-select" disabled>
                <option value="">— Select launch template —</option>
            </select>
            <input type="hidden" id="asg-template">
            <div id="asg-template-details" class="ec2-info-panel" hidden></div>
            <div class="form-text">Launch template defines the AMI, instance type, and config for each new EC2 instance in the group</div>
        </div>

        <div class="mb-4">
            <h6 class="text-primary fw-semibold mb-3">📊 Capacity Settings</h6>
            <p class="small text-muted mb-3">Control how many instances run at minimum, normally, and maximum under load</p>

            <div class="asg-capacity-viz mb-3" id="asg-capacity-viz">
                <div class="asg-capacity-track">
                    <div class="asg-capacity-fill" id="asg-capacity-fill"></div>
                    <div class="asg-capacity-marker asg-marker-min" id="asg-marker-min"><span>Min</span><strong id="asg-viz-min">1</strong></div>
                    <div class="asg-capacity-marker asg-marker-desired" id="asg-marker-desired"><span>Desired</span><strong id="asg-viz-desired">2</strong></div>
                    <div class="asg-capacity-marker asg-marker-max" id="asg-marker-max"><span>Max</span><strong id="asg-viz-max">3</strong></div>
                </div>
            </div>

            <div class="row g-3">
                <div class="col-md-4">
                    <label for="asg-min" class="form-label fw-medium">Min Size</label>
                    <input type="number" class="form-control asg-cap-input" id="asg-min" value="1" min="0" max="100">
                    <div class="form-text">Always running (even when idle)</div>
                </div>
                <div class="col-md-4">
                    <label for="asg-desired" class="form-label fw-medium">Desired Capacity</label>
                    <input type="number" class="form-control asg-cap-input" id="asg-desired" value="2" min="0" max="100">
                    <div class="form-text">Target count right now</div>
                </div>
                <div class="col-md-4">
                    <label for="asg-max" class="form-label fw-medium">Max Size</label>
                    <input type="number" class="form-control asg-cap-input" id="asg-max" value="3" min="1" max="100">
                    <div class="form-text">Ceiling during peak traffic</div>
                </div>
            </div>
            <div id="asg-capacity-warning" class="alert alert-danger py-2 px-3 mt-3 small" hidden></div>
            <div id="asg-capacity-summary" class="ec2-info-panel mt-3"></div>
        </div>

        <div class="mb-4">
            <div class="d-flex justify-content-between align-items-center mb-3">
                <h6 class="text-primary fw-semibold mb-0">📍 Subnets (Network Zones) <span class="text-danger">*</span></h6>
                <button type="button" class="btn btn-sm btn-outline-primary" id="refresh-asg-subnets">↻ Fetch Subnets</button>
            </div>
            <div id="asg-subnet-loading" class="text-muted small mb-2">Loading subnets...</div>
            <div id="asg-subnet-list" class="asg-subnet-grid"></div>
            <div class="form-text mt-2">Select at least <strong>2 subnets in different availability zones</strong> for high availability</div>
            <input type="hidden" id="asg-subnets">
        </div>
    `;

    showModal('Create Auto Scaling Group', modalBody, async () => {
        const name = document.getElementById('asg-name').value.trim();
        const launchTemplate = document.getElementById('asg-template').value || document.getElementById('asg-template-select').value;
        const minSize = parseInt(document.getElementById('asg-min').value, 10);
        const maxSize = parseInt(document.getElementById('asg-max').value, 10);
        const desiredCapacity = parseInt(document.getElementById('asg-desired').value, 10);
        const subnets = getSelectedAsgSubnets();

        if (!name) {
            showToast('ASG name is required', 'error');
            return;
        }
        if (!/^[a-zA-Z0-9][a-zA-Z0-9-]*$/.test(name)) {
            showToast('ASG name: use letters, numbers, hyphens only', 'error');
            return;
        }
        if (!launchTemplate) {
            showToast('Please select a launch template', 'error');
            return;
        }
        if (!validateAsgCapacity(minSize, maxSize, desiredCapacity, true)) return;
        if (subnets.length < 1) {
            showToast('Select at least one subnet', 'error');
            return;
        }
        if (subnets.length < 2) {
            showToast('Recommend 2+ subnets in different AZs for high availability', 'info');
        }

        const submitBtn = document.getElementById('modal-submit');
        submitBtn.disabled = true;
        submitBtn.innerHTML = '<span class="spinner-border spinner-border-sm me-2"></span>Creating...';

        try {
            const response = await fetch(`${API_BASE_URL}/asg/groups`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ name, launchTemplate, minSize, maxSize, desiredCapacity, subnets })
            });

            const result = await response.json();
            if (response.ok) {
                showToast('Auto Scaling Group created successfully!', 'success');
                closeModal();
                refreshASG();
            } else {
                showToast(result.error || 'Failed to create ASG', 'error');
            }
        } catch (error) {
            showToast('Error creating ASG', 'error');
            console.error(error);
        } finally {
            submitBtn.disabled = false;
            submitBtn.textContent = 'Create ASG';
        }
    }, { size: 'xl', submitText: 'Create ASG', onShown: initAsgModal });
}

let asgCatalog = { templates: [], subnets: [] };

async function fetchAsgLaunchTemplates() {
    const loading = document.getElementById('asg-template-loading');
    const select = document.getElementById('asg-template-select');
    if (loading) loading.textContent = 'Fetching launch templates...';
    try {
        const res = await fetch(`${API_BASE_URL}/asg/launch-templates`);
        const data = await res.json();
        asgCatalog.templates = data.launchTemplates || [];
        renderAsgTemplateSelect();
        if (loading) loading.textContent = data.awsConnected
            ? `Found ${asgCatalog.templates.length} template(s) from AWS`
            : `${asgCatalog.templates.length} catalog template(s) — connect AWS for live list`;
    } catch {
        if (loading) loading.textContent = 'Failed to load templates';
    }
}

async function fetchAsgSubnets() {
    const loading = document.getElementById('asg-subnet-loading');
    if (loading) loading.textContent = 'Fetching subnets...';
    try {
        const res = await fetch(`${API_BASE_URL}/ec2/subnets`);
        const data = await res.json();
        asgCatalog.subnets = data.subnets || [];
        renderAsgSubnetList();
        if (loading) loading.textContent = data.awsConnected
            ? `Found ${asgCatalog.subnets.length} subnet(s) from AWS`
            : `${asgCatalog.subnets.length} catalog subnet(s) — connect AWS for live list`;
    } catch {
        if (loading) loading.textContent = 'Failed to load subnets';
    }
}

function renderAsgTemplateSelect() {
    const select = document.getElementById('asg-template-select');
    const hidden = document.getElementById('asg-template');
    if (!select) return;

    if (asgCatalog.templates.length === 0) {
        select.innerHTML = '<option value="">No launch templates found</option>';
        select.disabled = true;
        return;
    }

    select.innerHTML = '<option value="">— Select launch template —</option>' +
        asgCatalog.templates.map(t =>
            `<option value="${t.name}" data-id="${t.id || ''}">${t.name}${t.instanceType ? ` (${t.instanceType})` : ''}</option>`
        ).join('');
    select.disabled = false;

    select.value = asgCatalog.templates[0].name;
    if (hidden) hidden.value = asgCatalog.templates[0].name;
    showAsgTemplateDetails(asgCatalog.templates[0].name);
}

function showAsgTemplateDetails(name) {
    const panel = document.getElementById('asg-template-details');
    const t = asgCatalog.templates.find(x => x.name === name);
    if (!panel || !t) {
        if (panel) panel.hidden = true;
        return;
    }
    panel.hidden = false;
    panel.innerHTML = `
        <div class="ec2-info-grid">
            <span><strong>Template:</strong> ${t.name}</span>
            <span><strong>ID:</strong> <code>${t.id || '—'}</code></span>
            <span><strong>Version:</strong> ${t.version || 1}</span>
            ${t.instanceType ? `<span><strong>Instance:</strong> ${t.instanceType}</span>` : ''}
            ${t.amiId ? `<span><strong>AMI:</strong> <code>${t.amiId}</code></span>` : ''}
        </div>
        <p class="mb-0 mt-2 small text-muted">${t.description || 'Server blueprint used when scaling adds new instances'}</p>
    `;
}

function renderAsgSubnetList() {
    const list = document.getElementById('asg-subnet-list');
    if (!list) return;

    if (asgCatalog.subnets.length === 0) {
        list.innerHTML = '<p class="text-muted small">No subnets available</p>';
        return;
    }

    list.innerHTML = asgCatalog.subnets.map(sn => `
        <label class="asg-subnet-card">
            <input type="checkbox" class="asg-subnet-check" value="${sn.id}" data-az="${sn.az}">
            <div class="asg-subnet-inner">
                <strong>${sn.name}</strong>
                <span class="asg-subnet-id"><code>${sn.id}</code></span>
                <span class="asg-subnet-meta">${sn.az} · ${sn.cidr}${sn.public ? ' · Public' : ' · Private'}</span>
            </div>
        </label>
    `).join('');

    list.querySelectorAll('.asg-subnet-check').forEach(cb => {
        cb.addEventListener('change', updateAsgSubnetHidden);
    });

    const defaults = asgCatalog.subnets.slice(0, 2);
    defaults.forEach(sn => {
        const cb = list.querySelector(`input[value="${sn.id}"]`);
        if (cb) cb.checked = true;
    });
    updateAsgSubnetHidden();
}

function getSelectedAsgSubnets() {
    return [...document.querySelectorAll('.asg-subnet-check:checked')].map(cb => cb.value);
}

function updateAsgSubnetHidden() {
    const hidden = document.getElementById('asg-subnets');
    const selected = getSelectedAsgSubnets();
    if (hidden) hidden.value = selected.join(',');
}

function validateAsgCapacity(min, max, desired, showToastOnError) {
    const warn = document.getElementById('asg-capacity-warning');
    let msg = '';
    if (min > max) msg = 'Min size cannot be greater than Max size';
    else if (desired < min) msg = 'Desired capacity cannot be less than Min size';
    else if (desired > max) msg = 'Desired capacity cannot exceed Max size';
    if (warn) {
        warn.hidden = !msg;
        warn.textContent = msg;
    }
    if (msg && showToastOnError) showToast(msg, 'error');
    return !msg;
}

function updateAsgCapacityViz() {
    const min = parseInt(document.getElementById('asg-min')?.value || 0, 10);
    const max = parseInt(document.getElementById('asg-max')?.value || 1, 10);
    const desired = parseInt(document.getElementById('asg-desired')?.value || 0, 10);

    validateAsgCapacity(min, max, desired, false);

    const range = Math.max(max, 1);
    const minPct = (min / range) * 100;
    const desiredPct = (desired / range) * 100;
    const maxPct = 100;

    document.getElementById('asg-viz-min').textContent = min;
    document.getElementById('asg-viz-desired').textContent = desired;
    document.getElementById('asg-viz-max').textContent = max;

    const fill = document.getElementById('asg-capacity-fill');
    if (fill) fill.style.width = `${desiredPct}%`;

    const setMarker = (id, pct) => {
        const el = document.getElementById(id);
        if (el) el.style.left = `calc(${Math.min(pct, 100)}% - 20px)`;
    };
    setMarker('asg-marker-min', minPct);
    setMarker('asg-marker-desired', desiredPct);
    setMarker('asg-marker-max', maxPct);

    const summary = document.getElementById('asg-capacity-summary');
    if (summary) {
        summary.innerHTML = `
            <strong>Scaling behavior:</strong>
            <p class="mb-0 mt-1 small">
                Always keep at least <strong>${min}</strong> instance(s) running.
                Target <strong>${desired}</strong> under normal load.
                Scale up to <strong>${max}</strong> during traffic spikes.
                CloudWatch alarms trigger scale-out/in automatically.
            </p>
        `;
    }
}

function initAsgModal() {
    ServiceDiagram.init();
    fetchAsgLaunchTemplates();
    fetchAsgSubnets();
    updateAsgCapacityViz();

    document.getElementById('refresh-asg-templates')?.addEventListener('click', fetchAsgLaunchTemplates);
    document.getElementById('refresh-asg-subnets')?.addEventListener('click', fetchAsgSubnets);

    document.getElementById('asg-template-select')?.addEventListener('change', (e) => {
        const hidden = document.getElementById('asg-template');
        if (hidden) hidden.value = e.target.value;
        showAsgTemplateDetails(e.target.value);
    });

    document.querySelectorAll('.asg-cap-input').forEach(input => {
        input.addEventListener('input', updateAsgCapacityViz);
    });
}

function refreshASG() {
    loadASGs();
}

// ========== ACM Functions ==========

async function loadCertificates() {
    const contentEl = document.getElementById('acm-content');
    contentEl.innerHTML = '<div class="loading">Loading certificates...</div>';
    
    try {
        const response = await fetch(`${API_BASE_URL}/acm/certificates`);
        const data = await response.json();
        
        acmData = data.certificates || [];
        
        if (acmData.length > 0) {
            displayCertificates(acmData);
        } else {
            contentEl.innerHTML = '<p style="text-align:center;color:#6b7280;">No certificates found. Request one to get started!</p>';
        }
        
        updateMetrics();
    } catch (error) {
        contentEl.innerHTML = '<p style="text-align:center;color:#ef4444;">Error loading certificates</p>';
        console.error('ACM Load Error:', error);
    }
}

function displayCertificates(certificates) {
    const contentEl = document.getElementById('acm-content');
    let html = '';
    
    certificates.forEach(cert => {
        const statusClass = cert.status === 'ISSUED' ? 'status-active' : 'status-inactive';
        
        html += `
            <div class="resource-card animated-card">
                <div class="resource-header">
                    <div style="display:flex;align-items:center;gap:10px;">
                        <span class="resource-icon">🔒</span>
                        <span class="resource-name">${cert.domainName}</span>
                    </div>
                    <span class="resource-status ${statusClass}">
                        ${cert.status}
                    </span>
                </div>
                <div class="resource-details">
                    <div><strong>Type:</strong> ${cert.type}</div>
                    <div><strong>ARN:</strong> ${cert.arn.substring(0, 60)}...</div>
                    ${cert.createdAt ? `<div><strong>Created:</strong> ${new Date(cert.createdAt).toLocaleString()}</div>` : ''}
                </div>
            </div>
        `;
    });
    
    contentEl.innerHTML = html;
}

function requestCertificate() {
    const modalBody = `
        ${ServiceDiagram.render('acm')}
        <div class="form-group">
            <label>Domain Name</label>
            <input type="text" id="cert-domain" placeholder="example.com" />
            <small style="color:#6b7280;">Will also include *.example.com</small>
        </div>
        <div class="form-group">
            <label>Validation Method</label>
            <select id="cert-validation">
                <option value="DNS">DNS Validation</option>
                <option value="EMAIL">Email Validation</option>
            </select>
        </div>
    `;
    
    showModal('Request SSL Certificate', modalBody, async () => {
        const domainName = document.getElementById('cert-domain').value.trim();
        const validationMethod = document.getElementById('cert-validation').value;

        const err = FormValidation.validateAcmDomain(domainName);
        if (err) {
            showToast(err, 'error');
            return;
        }
        
        try {
            const response = await fetch(`${API_BASE_URL}/acm/certificates`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ domainName, validationMethod })
            });
            
            const result = await response.json();
            if (response.ok) {
                showToast('Certificate requested successfully!', 'success');
                closeModal();
                refreshACM();
            } else {
                showToast(result.error || 'Failed to request certificate', 'error');
            }
        } catch (error) {
            showToast('Error requesting certificate', 'error');
            console.error(error);
        }
    });
}

function refreshACM() {
    loadCertificates();
}
