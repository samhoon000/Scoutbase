import type {Metadata} from 'next'
import './globals.css'
export const metadata:Metadata={title:'ScoutBase — Find the companies that need you',description:'Discover companies likely to benefit from analytics expertise.'}
export default function RootLayout({children}:{children:React.ReactNode}){return <html lang="en"><body>{children}</body></html>}
