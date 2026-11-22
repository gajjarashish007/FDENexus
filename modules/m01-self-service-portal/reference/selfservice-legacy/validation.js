/** Shared form validation for SmartOps Portal dashboard & deploy flows */
const FormValidation = {
    APP_NAME_RE: /^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?$/,
    DOMAIN_RE: /^([a-zA-Z0-9]([a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?\.)+[a-zA-Z]{2,}$/,
    S3_BUCKET_RE: /^[a-z0-9]([a-z0-9.-]{1,61}[a-z0-9])?$/,
    AMI_ID_RE: /^ami-[a-f0-9]{8,17}$/i,
    SUBNET_ID_RE: /^subnet-[a-f0-9]{8,17}$/i,
    TABLE_NAME_RE: /^[a-zA-Z0-9_.-]{3,255}$/,
    KEY_NAME_RE: /^[a-zA-Z0-9_.-]{1,255}$/,
    ASG_NAME_RE: /^[a-zA-Z0-9][a-zA-Z0-9-]*$/,

    validateAppName(name) {
        if (!name) return 'Application name is required';
        if (name.length < 3) return 'Application name must be at least 3 characters';
        if (!this.APP_NAME_RE.test(name)) {
            return 'Use lowercase letters, numbers, hyphens only (3–63 chars)';
        }
        return null;
    },

    validateDomain(domain) {
        if (!domain) return 'Domain name is required';
        if (!this.DOMAIN_RE.test(domain)) return 'Enter a valid domain (e.g. app.example.com)';
        return null;
    },

    validateS3Bucket(name) {
        if (!name) return 'Bucket name is required';
        if (name.length < 3 || name.length > 63) return 'Bucket name must be 3–63 characters';
        if (!this.S3_BUCKET_RE.test(name)) return 'Use lowercase letters, numbers, dots, hyphens only';
        if (name.includes('..')) return 'Bucket name cannot contain consecutive dots';
        if (name.startsWith('xn--') || name.endsWith('-s3alias')) return 'Invalid bucket name';
        return null;
    },

    validateAmiId(ami) {
        if (!ami) return 'AMI ID is required';
        if (!this.AMI_ID_RE.test(ami)) return 'AMI must look like ami-0abcdef1234567890';
        return null;
    },

    validatePort(port, label = 'Port') {
        const n = parseInt(port, 10);
        if (Number.isNaN(n) || n < 1 || n > 65535) return `${label} must be between 1 and 65535`;
        return null;
    },

    validateAlbTimeout(timeout) {
        const n = parseInt(timeout, 10);
        if (Number.isNaN(n) || n < 1 || n > 4000) return 'ALB timeout must be between 1 and 4000 seconds';
        return null;
    },

    validateSubnetIds(subnets) {
        if (!subnets || subnets.length === 0) return 'Select at least one subnet';
        for (const s of subnets) {
            if (!this.SUBNET_ID_RE.test(s)) return `Invalid subnet ID: ${s}`;
        }
        if (subnets.length < 2) return 'WARN: Recommend 2+ subnets in different availability zones';
        return null;
    },

    validateFileExtension(file, allowed, label) {
        if (!file) return `${label} is required`;
        const ext = '.' + file.name.split('.').pop().toLowerCase();
        if (!allowed.includes(ext)) return `${label} must be ${allowed.join(', ')}`;
        return null;
    },

    validateFileSize(file, maxBytes, label) {
        if (file && file.size > maxBytes) {
            const mb = Math.round(maxBytes / (1024 * 1024));
            return `${label} exceeds ${mb}MB limit`;
        }
        return null;
    },

    validateAcmDomain(domain) {
        if (!domain) return 'Domain name is required';
        const check = domain.startsWith('*.') ? domain.slice(2) : domain;
        if (!this.DOMAIN_RE.test(check)) return 'Enter a valid domain (e.g. app.example.com or *.example.com)';
        return null;
    },

    validateAsgName(name) {
        if (!name) return 'ASG name is required';
        if (!this.ASG_NAME_RE.test(name)) return 'ASG name: letters, numbers, hyphens only';
        return null;
    },

    validateAsgCapacity(min, max, desired) {
        min = parseInt(min, 10);
        max = parseInt(max, 10);
        desired = parseInt(desired, 10);
        if (min > desired) return 'Minimum capacity cannot exceed desired capacity';
        if (desired > max) return 'Desired capacity cannot exceed maximum capacity';
        if (min > max) return 'Minimum capacity cannot exceed maximum capacity';
        return null;
    },

    /** Run validators; returns first error string or null. Warn strings start with WARN: */
    firstError(...checks) {
        for (const msg of checks) {
            if (msg && !msg.startsWith('WARN:')) return msg;
        }
        return null;
    },
};
