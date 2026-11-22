// ========== Deployment Services ==========

function uploadFormData(url, formData, onProgress) {
    return new Promise((resolve, reject) => {
        const xhr = new XMLHttpRequest();
        xhr.open('POST', url);
        xhr.upload.onprogress = (e) => {
            if (e.lengthComputable && onProgress) {
                onProgress(Math.round((e.loaded / e.total) * 100));
            }
        };
        xhr.onload = () => {
            try {
                const data = JSON.parse(xhr.responseText);
                if (xhr.status >= 200 && xhr.status < 300) resolve(data);
                else reject(new Error(data.error || 'Upload failed'));
            } catch {
                reject(new Error('Invalid server response'));
            }
        };
        xhr.onerror = () => reject(new Error('Network error during upload'));
        xhr.send(formData);
    });
}

function showDeployResult(result) {
    const steps = (result.steps || []).map(s => `<li>${s}</li>`).join('');
    const dep = result.deployment || {};
    showToast(result.message, 'success');
    const resultHtml = `
        <div class="alert alert-success">
            <strong>✓ Deployment Successful</strong>
            ${dep.url ? `<p class="mb-0 mt-2"><a href="${dep.url}" target="_blank">${dep.url}</a></p>` : ''}
        </div>
        ${steps ? `<ol class="small text-muted mb-0">${steps}</ol>` : ''}
    `;
    const progressEl = document.getElementById('deploy-progress');
    if (progressEl) progressEl.innerHTML = resultHtml;
}

function setDeployProgress(percent, text) {
    const el = document.getElementById('deploy-progress');
    if (!el) return;
    el.innerHTML = `
        <div class="progress mb-2" style="height:8px;">
            <div class="progress-bar progress-bar-striped progress-bar-animated" style="width:${percent}%"></div>
        </div>
        <small class="text-muted">${text || 'Uploading...'} ${percent}%</small>
    `;
}

// ── Deploy Static Website Hosting ──
function deployStaticWebsiteHosting() {
    const modalBody = `
        ${ServiceDiagram.render('static-website')}
        <div class="alert alert-primary d-flex gap-3 align-items-start">
            <span class="fs-3">🌐</span>
            <div>
                <strong>Deploy Static Website Hosting</strong>
                <p class="mb-0 small text-muted">Upload HTML, CSS, JS and images — deployed to S3 with optional CloudFront CDN</p>
            </div>
        </div>
        <div class="mb-3">
            <label class="form-label fw-medium">Application Name <span class="text-danger">*</span></label>
            <input type="text" class="form-control" id="sw-app-name" placeholder="my-website">
        </div>
        <div class="mb-3">
            <label class="form-label fw-medium">Domain Name <span class="text-danger">*</span></label>
            <input type="text" class="form-control" id="sw-domain" placeholder="test.example.com">
            <div class="form-text">Custom domain for your website</div>
        </div>
        <div class="mb-3 form-check">
            <input type="checkbox" class="form-check-input" id="sw-cloudfront" checked>
            <label class="form-check-label" for="sw-cloudfront">Enable CloudFront CDN <small class="text-muted">(recommended)</small></label>
        </div>
        <div class="mb-3">
            <label class="form-label fw-medium">Website Files <span class="text-danger">*</span></label>
            <input type="file" class="form-control" id="sw-files" multiple webkitdirectory directory>
            <div class="form-text">Select folder with index.html, CSS, JS, images. Max 50MB per file.</div>
            <div id="sw-file-list" class="small text-muted mt-1"></div>
        </div>
        <div id="deploy-progress"></div>
    `;

    showModal('Deploy Static Website Hosting', modalBody, async () => {
        const appName = document.getElementById('sw-app-name').value.trim().toLowerCase();
        const domain = document.getElementById('sw-domain').value.trim();
        const cloudfront = document.getElementById('sw-cloudfront').checked;
        const files = document.getElementById('sw-files').files;

        const err = FormValidation.firstError(
            FormValidation.validateAppName(appName),
            FormValidation.validateDomain(domain),
            !files.length ? 'Please select website files' : null,
        );
        if (err) {
            showToast(err, 'error');
            return;
        }
        const hasIndex = Array.from(files).some(f => {
            const n = (f.webkitRelativePath || f.name).split('/').pop().toLowerCase();
            return n === 'index.html' || n === 'index.htm';
        });
        if (!hasIndex) {
            showToast('Upload must include index.html', 'error');
            return;
        }
        for (const f of files) {
            const sizeErr = FormValidation.validateFileSize(f, 50 * 1024 * 1024, f.name);
            if (sizeErr) { showToast(sizeErr, 'error'); return; }
        }

        const fd = new FormData();
        fd.append('appName', appName);
        fd.append('domain', domain);
        fd.append('cloudfront', cloudfront);
        for (const f of files) fd.append('files', f, f.webkitRelativePath || f.name);

        const btn = document.getElementById('modal-submit');
        btn.disabled = true;
        btn.innerHTML = '<span class="spinner-border spinner-border-sm me-2"></span>Deploying...';

        try {
            const result = await uploadFormData(`${API_BASE_URL}/deploy/static-website`, fd, setDeployProgress);
            showDeployResult(result);
            setTimeout(() => { closeModal(); refreshS3(); }, 2500);
        } catch (err) {
            showToast(err.message, 'error');
            btn.disabled = false;
            btn.textContent = 'Deploy Website';
        }
    }, {
        size: 'lg',
        submitText: 'Deploy Website',
        onShown: () => {
            document.getElementById('sw-files')?.addEventListener('change', (e) => {
                const list = document.getElementById('sw-file-list');
                list.textContent = e.target.files.length ? `${e.target.files.length} files selected` : '';
            });
        },
    });
}

// ── Upload Code → Docker Build → Deploy ──
function deployCodeUpload(mode) {
    const diagram = mode === 'lambda' ? ServiceDiagram.render('lambda') : ServiceDiagram.render('code-upload');
    const modalBody = `
        ${diagram}
        <div class="alert alert-info d-flex gap-3 align-items-start">
            <span class="fs-3">📦</span>
            <div>
                <strong>Upload Source Code → Build Docker Image</strong>
                <p class="mb-0 small">Upload a ZIP with HTML, Python, Node.js, Go, or Java code. We auto-detect the runtime, build a Docker image, push to ECR, and deploy.</p>
            </div>
        </div>
        <div class="row g-3">
            <div class="col-md-6">
                <label class="form-label fw-medium">Application Name <span class="text-danger">*</span></label>
                <input type="text" class="form-control" id="code-app-name" placeholder="my-app">
                <div class="form-text">Lowercase, letters, numbers, hyphens only</div>
            </div>
            <div class="col-md-6">
                <label class="form-label fw-medium">Language / Runtime</label>
                <select class="form-select" id="code-language">
                    <option value="auto">Auto-detect from ZIP</option>
                    <option value="python">Python</option>
                    <option value="nodejs">Node.js</option>
                    <option value="static">Static HTML (nginx)</option>
                    <option value="go">Go</option>
                    <option value="java">Java</option>
                </select>
            </div>
            <div class="col-md-6">
                <label class="form-label fw-medium">Container Port</label>
                <input type="number" class="form-control" id="code-port" value="8080" min="1" max="65535">
            </div>
            <div class="col-md-6">
                <label class="form-label fw-medium">Platform</label>
                <select class="form-select" id="code-platform">
                    <option value="linux/amd64">linux/amd64 (Intel/AMD)</option>
                    <option value="linux/arm64">linux/arm64 (Graviton/Apple Silicon)</option>
                </select>
            </div>
        </div>
        <div class="mb-3 mt-3">
            <label class="form-label fw-medium">Source Code ZIP <span class="text-danger">*</span></label>
            <input type="file" class="form-control" id="code-zip" accept=".zip">
            <div class="form-text">ZIP your project folder. Include Dockerfile if you have one. Max 200MB.</div>
            <div id="code-file-info" class="small text-muted mt-1"></div>
        </div>
        <div class="alert alert-secondary small mb-0">
            <strong>Supported:</strong> HTML/CSS/JS static sites · Python (Flask/FastAPI) · Node.js · Go · Java · Any language with a Dockerfile
        </div>
        <div id="deploy-progress" class="mt-3"></div>
    `;

    showModal(mode === 'lambda' ? 'Deploy Lambda Function' : 'Upload Code & Deploy', modalBody, async () => {
        const appName = document.getElementById('code-app-name').value.trim().toLowerCase();
        const language = document.getElementById('code-language').value;
        const containerPort = document.getElementById('code-port').value;
        const platform = document.getElementById('code-platform').value;
        const zip = document.getElementById('code-zip').files[0];

        const err = FormValidation.firstError(
            FormValidation.validateAppName(appName),
            FormValidation.validatePort(containerPort, 'Container port'),
            FormValidation.validateFileExtension(zip, ['.zip'], 'Source code ZIP'),
            FormValidation.validateFileSize(zip, 200 * 1024 * 1024, 'ZIP file'),
        );
        if (err) {
            showToast(err, 'error');
            return;
        }

        const fd = new FormData();
        fd.append('appName', appName);
        fd.append('language', language);
        fd.append('containerPort', containerPort);
        fd.append('platform', platform);
        fd.append('codeZip', zip);

        const btn = document.getElementById('modal-submit');
        btn.disabled = true;
        btn.innerHTML = '<span class="spinner-border spinner-border-sm me-2"></span>Building & Deploying...';

        try {
            const result = await uploadFormData(`${API_BASE_URL}/deploy/code-upload`, fd, setDeployProgress);
            showDeployResult(result);
            setTimeout(closeModal, 3000);
        } catch (err) {
            showToast(err.message, 'error');
            btn.disabled = false;
            btn.textContent = 'Build & Deploy';
        }
    }, {
        size: 'lg',
        submitText: 'Build & Deploy',
        onShown: () => {
            document.getElementById('code-zip')?.addEventListener('change', (e) => {
                const f = e.target.files[0];
                const info = document.getElementById('code-file-info');
                info.textContent = f ? `${f.name} (${formatBytes(f.size)})` : '';
            });
        },
    });
}

// Replace legacy static website with enhanced version
function createStaticWebsite() {
    deployStaticWebsiteHosting();
}
