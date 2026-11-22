// ========== 3D Service Architecture Diagrams ==========

const ServiceDiagram = {
    configs: {
        ec2: {
            title: 'EC2 Instance Architecture',
            subtitle: 'A virtual server in the cloud — like renting a computer that runs 24/7 in a data center.',
            theme: 'compute',
            nodes: [
                { icon: '👤', label: 'You', sub: 'SSH / Remote access' },
                { icon: '💻', label: 'EC2 Instance', sub: 'Virtual server (CPU + RAM)' },
                { icon: '🖼️', label: 'AMI', sub: 'OS + software template' },
                { icon: '🔑', label: 'Key Pair', sub: 'Secure login' },
                { icon: '🛡️', label: 'Security Group', sub: 'Firewall rules' },
            ],
            details: [
                { label: 'Instance Name', text: 'Friendly label to identify your server in the dashboard.' },
                { label: 'AMI (Image)', text: 'The operating system template — pick Amazon Linux, Ubuntu, or Windows. Click Fetch AMIs to load options.' },
                { label: 'Instance Type', text: 'Server size — vCPUs and RAM. Use tabs to filter Free Tier, General, Compute, or Memory types.' },
                { label: 'Key Pair', text: 'Optional SSH key (Linux) for secure remote login to your instance.' },
            ],
        },
        alb: {
            title: 'Application Load Balancer (ALB)',
            subtitle: 'Distributes incoming web traffic across multiple servers for high availability.',
            theme: 'network',
            nodes: [
                { icon: '🌍', label: 'Internet', sub: 'Users / browsers' },
                { icon: '🌐', label: 'ALB', sub: 'HTTP/HTTPS routing' },
                { icon: '💻', label: 'Target 1', sub: 'EC2 instance' },
                { icon: '💻', label: 'Target 2', sub: 'EC2 instance' },
                { icon: '📍', label: 'Subnets', sub: 'Multi-AZ placement' },
            ],
            details: [
                { label: 'Load Balancer Name', text: 'Unique name for this load balancer resource.' },
                { label: 'Subnets', text: 'At least 2 subnets in different availability zones for redundancy.' },
                { label: 'Scheme', text: 'Internet-facing (public) or internal (private VPC only).' },
                { label: 'Type', text: 'Application (ALB) for HTTP/HTTPS — best for web apps.' },
            ],
        },
        nlb: {
            title: 'Network Load Balancer (NLB)',
            subtitle: 'Ultra-low latency TCP/UDP traffic distribution with static IP support.',
            theme: 'network',
            nodes: [
                { icon: '⚡', label: 'Clients', sub: 'TCP/UDP traffic' },
                { icon: '🔌', label: 'NLB', sub: 'Layer 4 routing' },
                { icon: '🎯', label: 'Static IP', sub: 'Fixed endpoint' },
                { icon: '💻', label: 'Targets', sub: 'Backend servers' },
            ],
            details: [
                { label: 'Load Balancer Name', text: 'Unique identifier for your NLB.' },
                { label: 'Subnets', text: 'Place in multiple AZs for fault tolerance.' },
                { label: 'Type', text: 'Network (NLB) — best for TCP/UDP with sub-millisecond latency.' },
            ],
        },
        dynamodb: {
            title: 'DynamoDB Table Architecture',
            subtitle: 'Serverless NoSQL database — stores data as key-value pairs with millisecond response.',
            theme: 'database',
            nodes: [
                { icon: '📱', label: 'App', sub: 'Your application' },
                { icon: '🔑', label: 'Partition Key', sub: 'Primary lookup' },
                { icon: '📊', label: 'DynamoDB', sub: 'Managed table' },
                { icon: '🔄', label: 'Auto Scale', sub: 'On-demand capacity' },
                { icon: '💾', label: 'Backups', sub: 'Point-in-time recovery' },
            ],
            details: [
                { label: 'Table Name', text: 'Unique identifier — 3–255 chars, letters, numbers, underscores, hyphens, dots.' },
                { label: 'Partition Key', text: 'Required HASH key — distributes data (e.g. userId, orderId). Every item must have this.' },
                { label: 'Partition Key Type', text: 'String (S) for text IDs, Number (N) for numeric keys, Binary (B) for raw bytes.' },
                { label: 'Sort Key', text: 'Optional RANGE key — orders items within a partition (e.g. createdAt, version).' },
                { label: 'Billing Mode', text: 'On-Demand: pay per request, auto-scales. Provisioned: fixed capacity for steady traffic.' },
            ],
        },
        s3: {
            title: 'S3 Bucket Architecture',
            subtitle: 'Unlimited object storage — store files, backups, images, and static websites.',
            theme: 'storage',
            nodes: [
                { icon: '📤', label: 'Upload', sub: 'Files & objects' },
                { icon: '🪣', label: 'S3 Bucket', sub: 'Storage container' },
                { icon: '🔐', label: 'Encryption', sub: 'At rest' },
                { icon: '🌍', label: 'Access', sub: 'Public or private' },
            ],
            details: [
                { label: 'Bucket Name', text: 'Globally unique name — like a folder name in the cloud.' },
                { label: 'Website Hosting', text: 'Optional — serve static HTML/CSS/JS directly from the bucket.' },
            ],
        },
        asg: {
            title: 'Auto Scaling Group Architecture',
            subtitle: 'Automatically adds or removes servers based on demand — keeps performance steady and costs optimized.',
            theme: 'compute',
            nodes: [
                { icon: '📈', label: 'CloudWatch', sub: 'Monitors CPU/traffic' },
                { icon: '📋', label: 'Launch Template', sub: 'Server blueprint' },
                { icon: '💻', label: 'EC2 Pool', sub: 'Min → Desired → Max' },
                { icon: '🌐', label: 'Load Balancer', sub: 'Distributes traffic' },
                { icon: '📍', label: 'Subnets', sub: 'AZ placement' },
            ],
            details: [
                { label: 'ASG Name', text: 'Unique identifier — e.g. prod-web-asg. Letters, numbers, hyphens only.' },
                { label: 'Launch Template', text: 'Blueprint with AMI + instance type. Fetch templates or pick from the dropdown.' },
                { label: 'Min Size', text: 'Minimum instances always running — never scales below this.' },
                { label: 'Desired Capacity', text: 'Target instance count under normal load. Must be between Min and Max.' },
                { label: 'Max Size', text: 'Maximum instances during traffic spikes — cost ceiling.' },
                { label: 'Subnets', text: 'Network zones for new instances. Pick 2+ subnets in different AZs.' },
            ],
        },
        acm: {
            title: 'SSL Certificate Architecture',
            subtitle: 'Free HTTPS certificates — encrypts traffic between users and your website.',
            theme: 'security',
            nodes: [
                { icon: '🔒', label: 'ACM', sub: 'Certificate manager' },
                { icon: '🌐', label: 'Domain', sub: 'example.com' },
                { icon: '✅', label: 'Validation', sub: 'DNS or email proof' },
                { icon: '🔐', label: 'HTTPS', sub: 'Encrypted traffic' },
                { icon: '🌍', label: 'ALB / CloudFront', sub: 'Attaches cert' },
            ],
            details: [
                { label: 'Domain Name', text: 'Your website domain — wildcard *.example.com included automatically.' },
                { label: 'Validation Method', text: 'DNS (recommended) — add a CNAME record to prove ownership.' },
            ],
        },
        'static-website': {
            title: 'Static Website Architecture',
            subtitle: 'Host HTML, CSS, and JavaScript files on S3 with optional global CDN delivery.',
            theme: 'storage',
            nodes: [
                { icon: '📁', label: 'Your Files', sub: 'HTML, CSS, JS' },
                { icon: '🪣', label: 'S3 Bucket', sub: 'File storage' },
                { icon: '🌍', label: 'CloudFront', sub: 'Global CDN' },
                { icon: '🔗', label: 'Domain', sub: 'Custom URL' },
            ],
            details: [
                { label: 'Application Name', text: 'Label for this deployment in the portal.' },
                { label: 'Domain Name', text: 'The URL where users will access your site.' },
                { label: 'CloudFront CDN', text: 'Caches content worldwide for faster page loads.' },
            ],
        },
        'code-upload': {
            title: 'Code Upload & Deploy Architecture',
            subtitle: 'Upload source code — we detect the language, build a Docker image, and deploy to the cloud.',
            theme: 'deploy',
            nodes: [
                { icon: '📦', label: 'ZIP Upload', sub: 'Source code' },
                { icon: '🔍', label: 'Auto-detect', sub: 'Python, Node, Go…' },
                { icon: '🐳', label: 'Docker Build', sub: 'Container image' },
                { icon: '☁️', label: 'ECR + ECS', sub: 'Cloud deploy' },
                { icon: '🌐', label: 'Live URL', sub: 'Your app online' },
            ],
            details: [
                { label: 'Application Name', text: 'Unique name for your deployed app.' },
                { label: 'Language', text: 'Auto-detect or pick Python, Node.js, Go, Java, or static HTML.' },
                { label: 'Container Port', text: 'Port your app listens on inside the container.' },
            ],
        },
        ecs: {
            title: 'ECS Fargate Container Architecture',
            subtitle: 'Run containers without managing servers — fully managed serverless compute.',
            theme: 'deploy',
            nodes: [
                { icon: '🐳', label: 'Container', sub: 'Your app image' },
                { icon: '🚢', label: 'ECS Fargate', sub: 'Serverless runtime' },
                { icon: '📦', label: 'ECR', sub: 'Image registry' },
                { icon: '🌐', label: 'ALB', sub: 'Traffic routing' },
            ],
            details: [
                { label: 'No servers to manage', text: 'Fargate runs your container — you only provide the image.' },
                { label: 'Auto scaling', text: 'Scale task count based on traffic automatically.' },
            ],
        },
        lambda: {
            title: 'Lambda Function Architecture',
            subtitle: 'Run code on-demand — no servers, pay only when your function executes.',
            theme: 'compute',
            nodes: [
                { icon: '⚡', label: 'Trigger', sub: 'API, event, schedule' },
                { icon: 'λ', label: 'Lambda', sub: 'Your function code' },
                { icon: '📤', label: 'Response', sub: 'Return result' },
                { icon: '💰', label: 'Pay per use', sub: 'No idle cost' },
            ],
            details: [
                { label: 'Event-driven', text: 'Runs when triggered — HTTP request, file upload, schedule, etc.' },
                { label: 'Languages', text: 'Python, Node.js, Go, Java supported via code upload flow.' },
            ],
        },
        rds: {
            title: 'RDS Database Architecture',
            subtitle: 'Managed relational database — PostgreSQL, MySQL, and more with automated backups.',
            theme: 'database',
            nodes: [
                { icon: '📱', label: 'Application', sub: 'Connects via SQL' },
                { icon: '🗄️', label: 'RDS Instance', sub: 'Managed DB' },
                { icon: '🔄', label: 'Multi-AZ', sub: 'High availability' },
                { icon: '💾', label: 'Backups', sub: 'Automated daily' },
            ],
            details: [
                { label: 'Managed service', text: 'AWS handles patching, backups, and failover.' },
                { label: 'Engines', text: 'PostgreSQL, MySQL, MariaDB, Oracle, SQL Server.' },
            ],
        },
    },

    render(serviceId, options = {}) {
        const base = this.configs[serviceId] || this.configs[options.fallback] || null;
        if (!base) return '';

        const cfg = { ...base };
        if (serviceId === 'alb' && options.variant === 'network') {
            Object.assign(cfg, this.configs.nlb);
        }

        const nodesHtml = cfg.nodes.map((n, i) => `
            <div class="svc-node-3d" data-node="${i}" style="--node-i:${i}">
                <div class="svc-node-cube">
                    <div class="svc-node-face nf-front">${n.icon}</div>
                    <div class="svc-node-face nf-top">${i + 1}</div>
                </div>
                <strong class="svc-node-label">${n.label}</strong>
                <span class="svc-node-sub">${n.sub}</span>
            </div>
            ${i < cfg.nodes.length - 1 ? '<div class="svc-connector-3d"><div class="svc-connector-line"></div><div class="svc-connector-dot"></div></div>' : ''}
        `).join('');

        const detailsHtml = cfg.details.map(d => `
            <div class="svc-detail-item">
                <strong>${d.label}</strong>
                <p>${d.text}</p>
            </div>
        `).join('');

        return `
            <div class="svc-arch-wrap theme-${cfg.theme}" data-service-diagram="${serviceId}">
                <div class="svc-arch-header">
                    <h4>${cfg.title}</h4>
                    <p>${cfg.subtitle}</p>
                </div>
                <div class="svc-arch-scene">
                    ${nodesHtml}
                </div>
                <div class="svc-arch-details">
                    <h5>📋 Field Guide</h5>
                    <div class="svc-details-grid">${detailsHtml}</div>
                </div>
            </div>
        `;
    },

    renderMini(serviceId, options = {}) {
        const cfg = serviceId === 'alb' && options.variant === 'network' ? 'nlb' : serviceId;
        const inner = this.render(serviceId, options);
        if (!inner) return '';
        return inner
            .replace('svc-arch-wrap', 'svc-arch-wrap svc-arch-mini')
            .replace('svc-arch-details', 'svc-arch-details d-none');
    },

    init() {
        document.querySelectorAll('[data-service-diagram]').forEach(wrap => {
            const nodes = wrap.querySelectorAll('.svc-node-3d');
            nodes.forEach((node, i) => {
                node.addEventListener('mouseenter', () => {
                    nodes.forEach(n => n.classList.remove('active'));
                    node.classList.add('active');
                    wrap.style.setProperty('--active-step', i);
                });
            });
            if (nodes[0]) nodes[0].classList.add('active');
        });
    },

    initCardPreviews() {
        document.querySelectorAll('.service-card[data-service]').forEach(card => {
            const id = card.dataset.service;
            const slot = card.querySelector('.svc-card-arch');
            const variant = card.dataset.variant;
            if (slot && this.configs[id]) {
                slot.innerHTML = this.renderMini(id, { variant });
            }
        });
    },
};

document.addEventListener('DOMContentLoaded', () => {
    ServiceDiagram.initCardPreviews();
});
