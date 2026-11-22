// API Configuration
const API_BASE_URL = `${window.location.origin}/api`;
let currentRegion = 'eu-west-1';

// Charts removed - using card-based display

// Data cache
let ec2Data = [];
let dynamodbData = [];
let albData = [];
let s3Data = [];
let asgData = [];
let acmData = [];

// Initialize Dashboard
document.addEventListener('DOMContentLoaded', () => {
    checkConnection();
    loadAllData();
    
    // Auto-refresh every 30 seconds
    setInterval(loadAllData, 30000);
});

function loadAllData() {
    loadEC2Instances();
    loadDynamoDBTables();
    loadALBs();
    loadS3Buckets();
    loadASGs();
    loadCertificates();
}

// Connection Status
async function checkConnection() {
    const statusEl = document.getElementById('connection-status');
    try {
        const response = await fetch(`${API_BASE_URL}/health`);
        if (response.ok) {
            const data = await response.json();
            statusEl.textContent = '✓ Connected';
            statusEl.classList.add('connected');
            
            // Update region display if different
            if (data.region && data.region !== currentRegion) {
                currentRegion = data.region;
                const regionSelect = document.getElementById('region-select');
                if (regionSelect) {
                    regionSelect.value = data.region;
                }
            }
        } else {
            throw new Error('Connection failed');
        }
    } catch (error) {
        statusEl.textContent = '✗ Disconnected';
        statusEl.classList.add('disconnected');
        showToast('Backend connection failed. Please start the API server.', 'error');
    }
}

// ========== Monitoring & Charts ==========

function initializeCharts() {
    // Charts removed - using card-based display only
    console.log('Chart initialization skipped - using card layout');
}

function updateMetrics() {
    // EC2 Metrics
    const ec2Total = ec2Data.length;
    const ec2Running = ec2Data.filter(i => i.state === 'running').length;
    const ec2Stopped = ec2Data.filter(i => i.state === 'stopped').length;
    const ec2Pending = ec2Data.filter(i => i.state === 'pending').length;
    const ec2Terminated = ec2Data.filter(i => i.state === 'terminated').length;
    
    document.getElementById('ec2-total').textContent = ec2Total;
    document.getElementById('ec2-running').textContent = ec2Running;
    document.getElementById('ec2-stopped').textContent = ec2Stopped;
    
    // DynamoDB Metrics
    const dynamoTotal = dynamodbData.length;
    const dynamoActive = dynamodbData.filter(t => t.status === 'ACTIVE').length;
    const totalItems = dynamodbData.reduce((sum, t) => sum + (t.itemCount || 0), 0);
    const totalSize = dynamodbData.reduce((sum, t) => sum + (t.tableSizeBytes || 0), 0);
    
    if (document.getElementById('dynamodb-total')) {
        document.getElementById('dynamodb-total').textContent = dynamoTotal;
        document.getElementById('dynamodb-active').textContent = dynamoActive;
        document.getElementById('dynamodb-items').textContent = totalItems.toLocaleString();
        document.getElementById('storage-total').textContent = formatBytes(totalSize);
    }
    
    // ALB Metrics
    const albTotal = albData.length;
    const albActive = albData.filter(lb => lb.state === 'active').length;
    document.getElementById('alb-total').textContent = albTotal;
    document.getElementById('alb-active').textContent = albActive;
    
    // S3 Metrics
    const s3Total = s3Data.length;
    document.getElementById('s3-total').textContent = s3Total;
    
    // ASG Metrics
    const asgTotal = asgData.length;
    const asgInstances = asgData.reduce((sum, asg) => sum + (asg.instanceCount || 0), 0);
    document.getElementById('asg-total').textContent = asgTotal;
    document.getElementById('asg-instances').textContent = asgInstances;
    
    // ACM Metrics
    const acmTotal = acmData.length;
    const acmIssued = acmData.filter(cert => cert.status === 'ISSUED').length;
    if (document.getElementById('acm-total')) {
        document.getElementById('acm-total').textContent = acmTotal;
        document.getElementById('acm-issued').textContent = acmIssued;
    }
    
    // Health Status
    const totalResources = ec2Total + dynamoTotal + albTotal + s3Total + asgTotal + acmTotal;
    const healthStatus = totalResources > 0 ? 'Healthy' : 'No Resources';
    document.getElementById('health-status').textContent = healthStatus;
}

// ========== EC2 Functions ==========

async function loadEC2Instances() {
    const contentEl = document.getElementById('ec2-content');
    contentEl.innerHTML = '<div class="loading">Loading EC2 instances...</div>';
    
    try {
        const response = await fetch(`${API_BASE_URL}/ec2/instances`);
        const data = await response.json();
        
        ec2Data = data.instances || [];
        
        if (ec2Data.length > 0) {
            displayEC2Instances(ec2Data);
        } else {
            contentEl.innerHTML = '<p style="text-align:center;color:#6b7280;">No EC2 instances found. Launch one to get started!</p>';
        }
        
        updateMetrics();
    } catch (error) {
        contentEl.innerHTML = '<p style="text-align:center;color:#ef4444;">Error loading EC2 instances</p>';
        console.error('EC2 Load Error:', error);
    }
}

function displayEC2Instances(instances) {
    const contentEl = document.getElementById('ec2-content');
    let html = '';
    
    instances.forEach(instance => {
        const statusClass = instance.state === 'running' ? 'status-active' : 'status-inactive';
        
        html += `
            <div class="resource-card animated-card">
                <div class="resource-header">
                    <div style="display:flex;align-items:center;gap:10px;">
                        <span class="resource-icon">💻</span>
                        <span class="resource-name">${instance.name || instance.instanceId}</span>
                    </div>
                    <span class="resource-status ${statusClass}">
                        ${instance.state.toUpperCase()}
                    </span>
                </div>
                <div class="resource-details">
                    <div><strong>Instance ID:</strong> ${instance.instanceId}</div>
                    <div><strong>Type:</strong> ${instance.instanceType}</div>
                    <div><strong>Public IP:</strong> ${instance.publicIp || 'N/A'}</div>
                    <div><strong>Private IP:</strong> ${instance.privateIp || 'N/A'}</div>
                    <div><strong>Launch Time:</strong> ${new Date(instance.launchTime).toLocaleString()}</div>
                </div>
            </div>
        `;
    });
    
    contentEl.innerHTML = html;
}

function launchEC2Instance() {
    const modalBody = `
        ${ServiceDiagram.render('ec2')}
        <div class="alert alert-primary d-flex align-items-start gap-3 mb-4">
            <span class="fs-3">💻</span>
            <div>
                <strong class="d-block">Launch EC2 Instance</strong>
                <small class="text-muted">Pick an OS image (AMI), choose instance size, and launch your virtual server</small>
            </div>
        </div>

        <div class="mb-4">
            <h6 class="text-primary fw-semibold mb-3">📝 Instance Details</h6>
            <div class="mb-3">
                <label for="instance-name" class="form-label fw-medium">Instance Name</label>
                <input type="text" class="form-control" id="instance-name" placeholder="my-web-server">
                <div class="form-text">A friendly name to identify your instance in the dashboard</div>
            </div>
        </div>

        <div class="mb-4">
            <div class="d-flex justify-content-between align-items-center mb-3">
                <h6 class="text-primary fw-semibold mb-0">🖼️ AMI — Operating System Image</h6>
                <button type="button" class="btn btn-sm btn-outline-primary" id="refresh-amis-btn">↻ Fetch AMIs</button>
            </div>
            <div class="ec2-os-tabs mb-3" id="ec2-os-tabs">
                <button type="button" class="ec2-os-tab active" data-os="all">All</button>
                <button type="button" class="ec2-os-tab" data-os="amazon-linux">Amazon Linux</button>
                <button type="button" class="ec2-os-tab" data-os="ubuntu">Ubuntu</button>
                <button type="button" class="ec2-os-tab" data-os="windows">Windows</button>
            </div>
            <div id="ami-loading" class="text-muted small mb-2">Loading available AMIs...</div>
            <select class="form-select mb-2" id="ami-select" disabled>
                <option value="">— Select an AMI —</option>
            </select>
            <input type="hidden" id="ami-id">
            <div id="ami-details" class="ec2-info-panel" hidden></div>
            <div class="form-text">AMI = the OS template (Linux, Ubuntu, or Windows) pre-installed on your instance</div>
        </div>

        <div class="mb-4">
            <div class="d-flex justify-content-between align-items-center mb-3">
                <h6 class="text-primary fw-semibold mb-0">⚙️ Instance Type — Size &amp; Power</h6>
            </div>
            <div class="ec2-os-tabs mb-3" id="ec2-type-tabs">
                <button type="button" class="ec2-os-tab active" data-category="all">All</button>
                <button type="button" class="ec2-os-tab" data-category="free-tier">Free Tier</button>
                <button type="button" class="ec2-os-tab" data-category="general">General</button>
                <button type="button" class="ec2-os-tab" data-category="compute">Compute</button>
                <button type="button" class="ec2-os-tab" data-category="memory">Memory</button>
            </div>
            <div id="instance-types-loading" class="text-muted small mb-2">Loading instance types...</div>
            <div class="row g-3" id="instance-type-grid"></div>
            <input type="hidden" id="instance-type" value="">
            <div id="instance-type-summary" class="ec2-info-panel mt-3" hidden></div>
        </div>

        <div class="mb-4">
            <h6 class="text-primary fw-semibold mb-3">🔑 Security</h6>
            <div class="mb-3">
                <label for="key-pair-select" class="form-label fw-medium">Key Pair <span class="text-muted fw-normal">(Optional)</span></label>
                <select class="form-select mb-2" id="key-pair-select">
                    <option value="">— No key pair / enter manually —</option>
                </select>
                <input type="text" class="form-control" id="key-name" placeholder="Or type key pair name manually">
                <div class="form-text">SSH key for Linux/Ubuntu access, or RDP password retrieval for Windows</div>
            </div>
        </div>

        <div class="alert alert-warning mb-0" id="cost-estimate-box">
            <strong>💰 Estimated Cost</strong>
            <p class="mb-0 mt-1 small" id="cost-estimate-text">Select an instance type to see pricing</p>
        </div>
    `;

    showModal('Launch EC2 Instance', modalBody, async () => {
        const instanceName = document.getElementById('instance-name').value;
        const amiId = document.getElementById('ami-id').value || document.getElementById('ami-select').value;
        const instanceType = document.getElementById('instance-type').value;
        const keySelect = document.getElementById('key-pair-select').value;
        const keyManual = document.getElementById('key-name').value.trim();
        const keyName = keySelect || keyManual;

        if (!instanceType) {
            showToast('Please select an instance type', 'error');
            return;
        }
        if (typeof FormValidation !== 'undefined') {
            const amiErr = FormValidation.validateAmiId(amiId);
            if (amiErr) {
                showToast(amiErr, 'error');
                return;
            }
        }

        const submitBtn = document.getElementById('modal-submit');
        submitBtn.disabled = true;
        submitBtn.innerHTML = '<span class="spinner-border spinner-border-sm me-2"></span>Launching...';

        try {
            const response = await fetch(`${API_BASE_URL}/ec2/instances`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ instanceName, amiId, instanceType, keyName })
            });

            const result = await response.json();
            if (response.ok) {
                showToast('EC2 Instance launched successfully!', 'success');
                closeModal();
                setTimeout(() => refreshEC2(), 1000);
            } else {
                showToast(result.error || 'Failed to launch instance', 'error');
            }
        } catch (error) {
            showToast('Error launching instance', 'error');
            console.error(error);
        } finally {
            submitBtn.disabled = false;
            submitBtn.textContent = 'Launch Instance';
        }
    }, { size: 'xl', submitText: 'Launch Instance', onShown: initEc2Modal });
}

let ec2Catalog = { instanceTypes: [], amis: [], keyPairs: [] };
let ec2OsFilter = 'all';
let ec2CategoryFilter = 'all';

async function fetchEc2InstanceTypes(category = 'all') {
    const loading = document.getElementById('instance-types-loading');
    if (loading) loading.textContent = 'Loading instance types...';
    try {
        const res = await fetch(`${API_BASE_URL}/ec2/instance-types?category=${category}`);
        const data = await res.json();
        ec2Catalog.instanceTypes = data.instanceTypes || [];
        renderInstanceTypeGrid();
        if (loading) loading.textContent = data.awsConnected ? 'Live pricing from AWS' : 'Using catalog (AWS offline)';
    } catch (err) {
        if (loading) loading.textContent = 'Failed to load instance types';
    }
}

async function fetchEc2Amis(os = 'all') {
    const loading = document.getElementById('ami-loading');
    const select = document.getElementById('ami-select');
    if (loading) loading.textContent = 'Fetching AMIs...';
    if (select) select.disabled = true;
    try {
        const res = await fetch(`${API_BASE_URL}/ec2/amis?os=${os}`);
        const data = await res.json();
        ec2Catalog.amis = data.amis || [];
        renderAmiSelect();
        if (loading) loading.textContent = data.awsConnected
            ? `Found ${ec2Catalog.amis.length} AMI(s) from AWS`
            : `Showing ${ec2Catalog.amis.length} catalog AMI(s) — connect AWS for live list`;
    } catch (err) {
        if (loading) loading.textContent = 'Failed to fetch AMIs';
    }
}

async function fetchEc2KeyPairs() {
    const select = document.getElementById('key-pair-select');
    if (!select) return;
    try {
        const res = await fetch(`${API_BASE_URL}/ec2/key-pairs`);
        const data = await res.json();
        ec2Catalog.keyPairs = data.keyPairs || [];
        select.innerHTML = '<option value="">— No key pair / enter manually —</option>' +
            ec2Catalog.keyPairs.map(k => `<option value="${k.name}">${k.name} (${k.type})</option>`).join('');
    } catch { /* ignore */ }
}

function renderAmiSelect() {
    const select = document.getElementById('ami-select');
    const hidden = document.getElementById('ami-id');
    if (!select) return;

    if (ec2Catalog.amis.length === 0) {
        select.innerHTML = '<option value="">No AMIs found for this OS</option>';
        select.disabled = true;
        return;
    }

    select.innerHTML = '<option value="">— Select an AMI —</option>' +
        ec2Catalog.amis.map(a => `<option value="${a.id}">${a.name} (${a.id})</option>`).join('');
    select.disabled = false;

    const defaultAmi = ec2Catalog.amis[0];
    select.value = defaultAmi.id;
    if (hidden) hidden.value = defaultAmi.id;
    showAmiDetails(defaultAmi.id);
}

function showAmiDetails(amiId) {
    const panel = document.getElementById('ami-details');
    const ami = ec2Catalog.amis.find(a => a.id === amiId);
    if (!panel || !ami) {
        if (panel) panel.hidden = true;
        return;
    }
    const osLabel = { 'amazon-linux': 'Amazon Linux', ubuntu: 'Ubuntu', windows: 'Windows' }[ami.os] || ami.os;
    panel.hidden = false;
    panel.innerHTML = `
        <div class="ec2-info-grid">
            <span><strong>AMI ID:</strong> <code>${ami.id}</code></span>
            <span><strong>OS:</strong> ${osLabel}</span>
            <span><strong>Architecture:</strong> ${ami.architecture}</span>
            <span><strong>Root:</strong> ${ami.rootDevice || 'ebs'}</span>
        </div>
        <p class="mb-0 mt-2 small text-muted">${ami.description || ami.name}</p>
    `;
}

function renderInstanceTypeGrid() {
    const grid = document.getElementById('instance-type-grid');
    if (!grid) return;

    if (ec2Catalog.instanceTypes.length === 0) {
        grid.innerHTML = '<div class="col-12 text-muted small">No instance types match this filter</div>';
        return;
    }

    grid.innerHTML = ec2Catalog.instanceTypes.map(it => `
        <div class="col-sm-6 col-lg-4">
            <div class="card instance-type-card h-100 border-light" role="button" tabindex="0"
                 data-type="${it.type}" data-price="${it.priceHour}" data-free="${it.freeTier}">
                <div class="card-body py-3">
                    <div class="d-flex justify-content-between align-items-start gap-2">
                        <strong class="text-primary">${it.type}</strong>
                        ${it.freeTier ? '<span class="badge bg-success">Free Tier</span>' : ''}
                    </div>
                    <small class="text-muted d-block mt-1">${it.vcpus} vCPU · ${it.memoryGb} GB RAM</small>
                    <small class="text-secondary d-block">${it.priceLabel}</small>
                    <small class="text-muted d-block mt-1 ec2-type-desc">${it.desc}</small>
                </div>
            </div>
        </div>
    `).join('');

    grid.querySelectorAll('.instance-type-card').forEach(card => {
        card.addEventListener('click', () => selectInstanceType(card.dataset.type));
        card.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault();
                selectInstanceType(card.dataset.type);
            }
        });
    });

    const current = document.getElementById('instance-type')?.value;
    const defaultType = current && ec2Catalog.instanceTypes.some(t => t.type === current)
        ? current
        : ec2Catalog.instanceTypes.find(t => t.freeTier)?.type || ec2Catalog.instanceTypes[0]?.type;
    if (defaultType) selectInstanceType(defaultType);
}

function initEc2Modal() {
    ServiceDiagram.init();
    ec2OsFilter = 'all';
    ec2CategoryFilter = 'all';

    document.querySelectorAll('#ec2-os-tabs .ec2-os-tab').forEach(tab => {
        tab.addEventListener('click', () => {
            document.querySelectorAll('#ec2-os-tabs .ec2-os-tab').forEach(t => t.classList.remove('active'));
            tab.classList.add('active');
            ec2OsFilter = tab.dataset.os;
            fetchEc2Amis(ec2OsFilter);
        });
    });

    document.querySelectorAll('#ec2-type-tabs .ec2-os-tab').forEach(tab => {
        tab.addEventListener('click', () => {
            document.querySelectorAll('#ec2-type-tabs .ec2-os-tab').forEach(t => t.classList.remove('active'));
            tab.classList.add('active');
            ec2CategoryFilter = tab.dataset.category;
            fetchEc2InstanceTypes(ec2CategoryFilter);
        });
    });

    document.getElementById('refresh-amis-btn')?.addEventListener('click', () => fetchEc2Amis(ec2OsFilter));

    document.getElementById('ami-select')?.addEventListener('change', (e) => {
        const id = e.target.value;
        const hidden = document.getElementById('ami-id');
        if (hidden) hidden.value = id;
        showAmiDetails(id);
    });

    document.getElementById('key-pair-select')?.addEventListener('change', (e) => {
        const manual = document.getElementById('key-name');
        if (manual && e.target.value) manual.value = e.target.value;
    });

    fetchEc2Amis('all');
    fetchEc2InstanceTypes('all');
    fetchEc2KeyPairs();
}

function selectInstanceType(type) {
    const input = document.getElementById('instance-type');
    if (!input) return;
    input.value = type;

    const it = ec2Catalog.instanceTypes.find(t => t.type === type);

    document.querySelectorAll('.instance-type-card').forEach(card => {
        const selected = card.dataset.type === type;
        card.classList.remove('border-primary', 'shadow-sm', 'bg-primary-subtle', 'border-light');
        if (selected) {
            card.classList.add('border-primary', 'shadow-sm', 'bg-primary-subtle');
        } else {
            card.classList.add('border-light');
        }
    });

    const costEl = document.getElementById('cost-estimate-text');
    const costBox = document.getElementById('cost-estimate-box');
    const summary = document.getElementById('instance-type-summary');

    if (it && summary) {
        summary.hidden = false;
        summary.innerHTML = `
            <strong>Selected: ${it.type}</strong>
            <div class="ec2-info-grid mt-2">
                <span><strong>vCPUs:</strong> ${it.vcpus}</span>
                <span><strong>Memory:</strong> ${it.memoryGb} GB</span>
                <span><strong>Category:</strong> ${it.category}</span>
                <span><strong>Price:</strong> ${it.priceLabel}</span>
            </div>
            <p class="mb-0 mt-2 small">${it.desc} — ${it.priceDetail}</p>
        `;
    }

    if (costEl && it) {
        costEl.innerHTML = `${it.type}: <strong>${it.priceLabel}</strong> ${it.priceDetail}`;
    }
    if (costBox && it) {
        costBox.className = it.freeTier ? 'alert alert-warning mb-0' : 'alert alert-info mb-0';
    }
}

function refreshEC2() {
    loadEC2Instances();
}

// ========== DynamoDB Functions ==========

async function loadDynamoDBTables() {
    const contentEl = document.getElementById('dynamodb-content');
    contentEl.innerHTML = '<div class="loading">Loading DynamoDB tables...</div>';
    
    try {
        const response = await fetch(`${API_BASE_URL}/dynamodb/tables`);
        const data = await response.json();
        
        dynamodbData = data.tables || [];
        
        if (dynamodbData.length > 0) {
            displayDynamoDBTables(dynamodbData);
        } else {
            contentEl.innerHTML = '<p style="text-align:center;color:#6b7280;">No DynamoDB tables found. Create one to get started!</p>';
        }
        
        updateMetrics();
    } catch (error) {
        contentEl.innerHTML = '<p style="text-align:center;color:#ef4444;">Error loading DynamoDB tables</p>';
        console.error('DynamoDB Load Error:', error);
    }
}

function displayDynamoDBTables(tables) {
    const contentEl = document.getElementById('dynamodb-content');
    let html = '';
    
    tables.forEach(table => {
        html += `
            <div class="resource-card animated-card">
                <div class="resource-header">
                    <div style="display:flex;align-items:center;gap:10px;">
                        <span class="resource-icon">📊</span>
                        <span class="resource-name">${table.tableName}</span>
                    </div>
                    <span class="resource-status ${table.status === 'ACTIVE' ? 'status-active' : 'status-inactive'}">
                        ${table.status}
                    </span>
                </div>
                <div class="resource-details">
                    <div><strong>Item Count:</strong> ${table.itemCount || 0}</div>
                    <div><strong>Size:</strong> ${formatBytes(table.tableSizeBytes || 0)}</div>
                    <div><strong>Created:</strong> ${table.creationDateTime ? new Date(table.creationDateTime).toLocaleDateString() : 'N/A'}</div>
                </div>
            </div>
        `;
    });
    
    contentEl.innerHTML = html;
}

function createDynamoDBTable(mode) {
    const isRds = mode === 'rds';
    const diagram = isRds ? ServiceDiagram.render('rds') : ServiceDiagram.render('dynamodb');
    const modalBody = `
        ${diagram}
        <div class="alert alert-primary d-flex gap-3 align-items-start mb-4">
            <span class="fs-3">${isRds ? '🗄️' : '📊'}</span>
            <div>
                <strong>${isRds ? 'Create RDS Database' : 'Create DynamoDB Table'}</strong>
                <p class="mb-0 small text-muted">${isRds
                    ? 'Managed relational database — use the DynamoDB-style form below for demo, or contact admin for RDS provisioning'
                    : 'Serverless NoSQL database — define how your data is organized with keys and billing mode'}</p>
            </div>
        </div>

        <div class="mb-4">
            <h6 class="text-primary fw-semibold mb-3">📛 Table Identity</h6>
            <label for="table-name" class="form-label fw-medium">Table Name <span class="text-danger">*</span></label>
            <input type="text" class="form-control ddb-field" id="table-name" placeholder="my-table" maxlength="255">
            <div class="form-text">Unique name for this table. Use 3–255 characters: letters, numbers, underscores, hyphens, dots (e.g. <code>Users</code>, <code>OrderItems</code>)</div>
        </div>

        <div class="mb-4">
            <h6 class="text-primary fw-semibold mb-3">🔑 Primary Key Schema</h6>
            <p class="small text-muted mb-3">Every item needs a unique key. The <strong>partition key</strong> distributes data; an optional <strong>sort key</strong> orders items within a partition.</p>

            <div class="row g-3">
                <div class="col-md-6">
                    <label for="partition-key" class="form-label fw-medium">Partition Key <span class="text-danger">*</span></label>
                    <input type="text" class="form-control ddb-field" id="partition-key" placeholder="userId">
                    <div class="form-text">Primary lookup — e.g. <code>userId</code>, <code>orderId</code>, <code>pk</code></div>
                </div>
                <div class="col-md-6">
                    <label for="partition-key-type" class="form-label fw-medium">Partition Key Type</label>
                    <select class="form-select ddb-field" id="partition-key-type">
                        <option value="S">String (S) — text IDs, emails, UUIDs</option>
                        <option value="N">Number (N) — numeric IDs stored as strings</option>
                        <option value="B">Binary (B) — raw binary data</option>
                    </select>
                </div>
                <div class="col-md-6">
                    <label for="sort-key" class="form-label fw-medium">Sort Key <span class="text-muted fw-normal">(Optional)</span></label>
                    <input type="text" class="form-control ddb-field" id="sort-key" placeholder="createdAt">
                    <div class="form-text">Sorts items within the same partition — e.g. <code>timestamp</code>, <code>version</code></div>
                </div>
                <div class="col-md-6">
                    <label for="sort-key-type" class="form-label fw-medium">Sort Key Type</label>
                    <select class="form-select ddb-field" id="sort-key-type" disabled>
                        <option value="S">String (S)</option>
                        <option value="N">Number (N)</option>
                        <option value="B">Binary (B)</option>
                    </select>
                    <div class="form-text">Enabled when a sort key name is entered</div>
                </div>
            </div>

            <div id="ddb-schema-preview" class="ddb-schema-preview mt-3"></div>
        </div>

        <div class="mb-4">
            <h6 class="text-primary fw-semibold mb-3">💰 Billing Mode</h6>
            <div class="row g-3" id="ddb-billing-cards">
                <div class="col-md-6">
                    <div class="ddb-billing-card active" role="button" tabindex="0" data-mode="PAY_PER_REQUEST">
                        <strong>On-Demand</strong>
                        <span class="badge bg-success ms-2">Recommended</span>
                        <p class="small text-muted mb-0 mt-2">Pay per read/write request. Auto-scales with traffic — best for most workloads and unpredictable traffic.</p>
                    </div>
                </div>
                <div class="col-md-6">
                    <div class="ddb-billing-card" role="button" tabindex="0" data-mode="PROVISIONED">
                        <strong>Provisioned</strong>
                        <p class="small text-muted mb-0 mt-2">Set fixed read/write capacity units. Lower cost for steady, predictable traffic — you manage scaling.</p>
                    </div>
                </div>
            </div>
            <input type="hidden" id="billing-mode" value="PAY_PER_REQUEST">
            <div id="ddb-billing-summary" class="ec2-info-panel mt-3"></div>
        </div>

        <div id="ddb-validation-warning" class="alert alert-danger py-2 px-3 small" hidden></div>
    `;

    showModal(isRds ? 'Create RDS Database' : 'Create DynamoDB Table', modalBody, async () => {
        const tableName = document.getElementById('table-name').value.trim();
        const partitionKey = document.getElementById('partition-key').value.trim();
        const partitionKeyType = document.getElementById('partition-key-type').value;
        const sortKey = document.getElementById('sort-key').value.trim();
        const sortKeyType = document.getElementById('sort-key-type').value;
        const billingMode = document.getElementById('billing-mode').value;

        if (!validateDynamoDbForm(true)) return;

        const submitBtn = document.getElementById('modal-submit');
        submitBtn.disabled = true;
        submitBtn.innerHTML = '<span class="spinner-border spinner-border-sm me-2"></span>Creating...';

        try {
            const response = await fetch(`${API_BASE_URL}/dynamodb/tables`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    tableName, partitionKey, partitionKeyType,
                    sortKey: sortKey || undefined,
                    sortKeyType: sortKey ? sortKeyType : undefined,
                    billingMode,
                }),
            });

            const result = await response.json();
            if (response.ok) {
                showToast('DynamoDB Table created successfully!', 'success');
                closeModal();
                refreshDynamoDB();
            } else {
                showToast(result.error || 'Failed to create table', 'error');
            }
        } catch (error) {
            showToast('Error creating table', 'error');
            console.error(error);
        } finally {
            submitBtn.disabled = false;
            submitBtn.textContent = 'Create Table';
        }
    }, { size: 'xl', submitText: 'Create Table', onShown: initDynamoDbModal });
}

const DDB_TYPE_LABELS = { S: 'String', N: 'Number', B: 'Binary' };

function initDynamoDbModal() {
    ServiceDiagram.init();
    updateDynamoDbPreview();
    updateDynamoDbBillingSummary();

    document.querySelectorAll('.ddb-field').forEach(el => {
        el.addEventListener('input', updateDynamoDbPreview);
        el.addEventListener('change', updateDynamoDbPreview);
    });

    document.getElementById('sort-key')?.addEventListener('input', (e) => {
        const sortType = document.getElementById('sort-key-type');
        if (sortType) sortType.disabled = !e.target.value.trim();
    });

    document.querySelectorAll('.ddb-billing-card').forEach(card => {
        const activate = () => selectDynamoDbBilling(card.dataset.mode);
        card.addEventListener('click', activate);
        card.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault();
                activate();
            }
        });
    });
}

function selectDynamoDbBilling(mode) {
    document.getElementById('billing-mode').value = mode;
    document.querySelectorAll('.ddb-billing-card').forEach(card => {
        card.classList.toggle('active', card.dataset.mode === mode);
    });
    updateDynamoDbBillingSummary();
}

function updateDynamoDbBillingSummary() {
    const mode = document.getElementById('billing-mode')?.value;
    const el = document.getElementById('ddb-billing-summary');
    if (!el) return;
    if (mode === 'PAY_PER_REQUEST') {
        el.innerHTML = '<strong>On-Demand selected:</strong> No capacity planning needed. You pay per request — ideal for new apps and variable traffic.';
    } else {
        el.innerHTML = '<strong>Provisioned selected:</strong> You set read/write capacity units (RCU/WCU). Best when traffic is steady and predictable.';
    }
}

function updateDynamoDbPreview() {
    validateDynamoDbForm(false);

    const tableName = document.getElementById('table-name')?.value.trim() || 'my-table';
    const pk = document.getElementById('partition-key')?.value.trim() || 'id';
    const pkType = document.getElementById('partition-key-type')?.value || 'S';
    const sk = document.getElementById('sort-key')?.value.trim();
    const skType = document.getElementById('sort-key-type')?.value || 'S';
    const preview = document.getElementById('ddb-schema-preview');
    if (!preview) return;

    preview.innerHTML = `
        <div class="ddb-schema-title">📋 Schema Preview</div>
        <div class="ddb-schema-table">
            <div class="ddb-schema-row header">
                <span>Table</span><span>${tableName}</span>
            </div>
            <div class="ddb-schema-row">
                <span>Partition Key (HASH)</span>
                <span><code>${pk}</code> <em>(${DDB_TYPE_LABELS[pkType]})</em></span>
            </div>
            ${sk ? `
            <div class="ddb-schema-row">
                <span>Sort Key (RANGE)</span>
                <span><code>${sk}</code> <em>(${DDB_TYPE_LABELS[skType]})</em></span>
            </div>` : `
            <div class="ddb-schema-row muted">
                <span>Sort Key</span><span>None — single-key table</span>
            </div>`}
            <div class="ddb-schema-example">
                <strong>Example item:</strong>
                <code>{ "${pk}": "${pkType === 'N' ? '12345' : 'user-001'}"${sk ? `, "${sk}": "${skType === 'N' ? '1699999999' : '2026-08-05T12:00:00Z'}"` : ''}, "data": "..." }</code>
            </div>
        </div>
    `;
}

function validateDynamoDbForm(showToastOnError) {
    const tableName = document.getElementById('table-name')?.value.trim();
    const partitionKey = document.getElementById('partition-key')?.value.trim();
    const sortKey = document.getElementById('sort-key')?.value.trim();
    const warn = document.getElementById('ddb-validation-warning');
    let msg = '';

    if (!tableName) msg = 'Table name is required';
    else if (!/^[a-zA-Z0-9_.-]{3,255}$/.test(tableName)) msg = 'Table name: 3–255 chars, letters, numbers, _ . - only';
    else if (!partitionKey) msg = 'Partition key is required';
    else if (!/^[a-zA-Z0-9_.-]+$/.test(partitionKey)) msg = 'Partition key: letters, numbers, _ . - only';
    else if (sortKey && !/^[a-zA-Z0-9_.-]+$/.test(sortKey)) msg = 'Sort key: letters, numbers, _ . - only';
    else if (sortKey && sortKey === partitionKey) msg = 'Sort key must differ from partition key';

    if (warn) {
        warn.hidden = !msg;
        warn.textContent = msg;
    }
    if (msg && showToastOnError) showToast(msg, 'error');
    return !msg;
}

function refreshDynamoDB() {
    loadDynamoDBTables();
}

// ========== Modal Functions (Bootstrap 5) ==========

let bsModalInstance = null;

function showModal(title, body, onSubmit, fourth) {
    const modalEl = document.getElementById('modal');
    let onShown = null;
    let options = { size: 'lg', submitText: 'Submit' };

    if (typeof fourth === 'function') {
        onShown = fourth;
    } else if (fourth && typeof fourth === 'object') {
        onShown = fourth.onShown || null;
        options = { ...options, ...fourth };
    }

    const dialog = modalEl.querySelector('.modal-dialog');
    dialog.className = `modal-dialog modal-${options.size} modal-dialog-scrollable modal-dialog-centered`;

    document.getElementById('modal-title').textContent = title;
    document.getElementById('modal-body').innerHTML = body;

    const submitBtn = document.getElementById('modal-submit');
    submitBtn.disabled = false;
    submitBtn.textContent = options.submitText;
    submitBtn.onclick = onSubmit;

    if (!bsModalInstance) {
        bsModalInstance = bootstrap.Modal.getOrCreateInstance(modalEl, {
            backdrop: true,
            keyboard: true,
            focus: true,
        });
    }

    if (onShown) {
        modalEl.addEventListener('shown.bs.modal', function handler() {
            ServiceDiagram.init();
            onShown();
            modalEl.removeEventListener('shown.bs.modal', handler);
        });
    } else {
        modalEl.addEventListener('shown.bs.modal', function handler() {
            ServiceDiagram.init();
            modalEl.removeEventListener('shown.bs.modal', handler);
        });
    }

    bsModalInstance.show();
}

function closeModal() {
    const modalEl = document.getElementById('modal');
    const instance = bootstrap.Modal.getInstance(modalEl);
    if (instance) instance.hide();
}

// ========== Toast Notifications ==========

function showToast(message, type = 'info') {
    const toast = document.getElementById('toast');
    toast.textContent = message;
    toast.style.display = 'block';
    toast.className = 'toast align-items-center text-white border-0 position-fixed bottom-0 end-0 m-4 show';

    if (type === 'success') toast.classList.add('bg-success');
    else if (type === 'error') toast.classList.add('bg-danger');
    else toast.classList.add('bg-primary');

    setTimeout(() => {
        toast.classList.remove('show');
        toast.style.display = 'none';
    }, 3500);
}

// ========== Utility Functions ==========

function formatBytes(bytes) {
    if (bytes === 0) return '0 Bytes';
    const k = 1024;
    const sizes = ['Bytes', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return Math.round(bytes / Math.pow(k, i) * 100) / 100 + ' ' + sizes[i];
}


