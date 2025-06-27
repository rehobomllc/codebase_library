# Substance Abuse Treatment Locator Companion App

A web application that helps users find substance abuse and mental health treatment facilities and communicate with them.

## Features

- Search for treatment facilities by location
- Filter search results by various criteria
- View facility locations on a map
- Contact facilities through in-app messaging
- View and manage message threads with facilities

## Technology Stack

- Next.js (React framework)
- TypeScript
- Tailwind CSS for styling
- Prisma ORM with PostgreSQL database
- OpenStreetMap with Leaflet for location services
- Zapier integration for communication workflows

## Getting Started

### Prerequisites

- Node.js 18+ and npm
- PostgreSQL database

### Installation

1. Clone the repository
   ```bash
   git clone <repository-url>
   cd companion-app
   ```

2. Install dependencies
   ```bash
   npm install
   ```

3. Set up environment variables
   Create a `.env` file in the root directory with the following variables:
   ```
   DATABASE_URL="postgresql://postgres:password@localhost:5432/treatment_finder"
   ```

4. Initialize the database
   ```bash
   npx prisma migrate dev --name init
   ```

5. Start the development server
   ```bash
   npm run dev
   ```

6. Open [http://localhost:3000](http://localhost:3000) in your browser

## Development

### Database Schema

The application uses two main models:
- `Facility`: Represents a treatment facility with contact information and services
- `Message`: Represents a message between a user and a facility

See `prisma/schema.prisma` for the complete schema definition.

### Map Integration

The application uses OpenStreetMap with Leaflet for maps and geocoding:
- Nominatim service is used for geocoding addresses to coordinates
- Leaflet provides interactive maps with facility markers
- All mapping services are free to use with proper attribution

### API Routes

- `/api/samhsa`: Interfaces with the SAMHSA treatment facility locator API
- `/api/messages`: Manages message threads and messages
- `/api/zapier`: Webhook endpoints for Zapier integration

### Building for Production

```bash
npm run build
npm start
``` 