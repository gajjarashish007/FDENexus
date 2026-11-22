# AWS Cloud Dashboard - Service Cards

## Overview

The dashboard now includes a beautiful service cards view that displays all available AWS services in an organized, visual format.

## Files

- `dashboard.html` - Service cards landing page
- `dashboard-styles.css` - Styles for service cards
- `index.html` - Main monitoring dashboard (updated with navigation)

## Features

### Service Cards Layout

Each service card includes:

1. **Service Badge** - Color-coded category (Compute, Networking, Database, Storage, Security)
2. **Animated Icon** - Large emoji icon with bounce animation
3. **Service Title** - Clear service name
4. **Description** - Brief explanation of the service
5. **Metrics** - Key performance indicators (deploy time, cost, SLA, etc.)
6. **Feature Tags** - Quick highlights of key features
7. **Create Button** - Direct action button to create the resource

### Service Categories

**COMPUTE** (Blue)
- EC2 Instance
- Auto Scaling Group

**NETWORKING** (Yellow)
- Application Load Balancer
- Network Load Balancer

**DATABASE** (Pink)
- DynamoDB Table

**STORAGE** (Green)
- S3 Bucket
- Static Website

**SECURITY** (Red)
- SSL Certificate (ACM)

### Animations

- **Staggered Entry** - Cards appear one by one with delay
- **Hover Effects** - Cards lift up on hover
- **Icon Bounce** - Service icons have subtle bounce animation
- **Smooth Transitions** - All interactions are smooth

### Navigation

- **Available Services** button on main dashboard → Opens service cards view
- **View Resources** button on service cards → Returns to monitoring dashboard

## Usage

### Access Service Cards

1. Open `dashboard.html` directly
2. Or click "Available Services" button from main dashboard

### Create Resources

Click any "Create [Service]" button to open the creation modal for that service.

### Metrics Displayed

- **EC2**: Deploy time (2min), Cost ($0.01/hr)
- **ALB**: Deploy time (3min), Uptime SLA (99.9%)
- **NLB**: Deploy time (3min), Latency (<1ms)
- **DynamoDB**: Latency (<1ms), Scale (∞)
- **S3**: Durability (11 9's), Capacity (∞)
- **ASG**: Deploy time (5min), Scaling (Auto)
- **ACM**: Cost (Free), Renewal (Auto)
- **Static Website**: Deploy time (1min), CDN (Global)

## Responsive Design

- Desktop: 3-4 cards per row
- Tablet: 2 cards per row
- Mobile: 1 card per row (stacked)

## Color Scheme

Matches the main dashboard with:
- Purple gradient background
- White cards with colored badges
- Gradient buttons
- Consistent typography

## Future Enhancements

- Add service status indicators
- Show current resource counts per service
- Add cost estimates
- Include service documentation links
- Add favorite/pinned services
