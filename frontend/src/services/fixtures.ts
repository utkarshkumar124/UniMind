import type { Doc, Message, Conversation, Source } from './types'
const demo = (t:string)=>`[Demo content] ${t}`
export const docs:Doc[] = [
 {id:'d1',title:'Student Handbook (demo)',category:'Policy',department:'Academics',type:'pdf',uploaded:'2026-01-12',status:'processed',pages:48,
  preview:[demo('Sample page 1. Placeholder text for the handbook introduction.'),demo('Sample page 2. Placeholder text about attendance expectations; real thresholds will come from official documents.')]},
 {id:'d2',title:'Examination Rules (demo)',category:'Policy',department:'Examinations',type:'pdf',uploaded:'2026-02-03',status:'processed',pages:22,
  preview:[demo('Sample page 1. Placeholder exam conduct overview.'),demo('Sample page 2. Placeholder re-evaluation procedure outline.')]},
 {id:'d3',title:'Hostel Guidelines (demo)',category:'Policy',department:'Facilities',type:'docx',uploaded:'2026-02-20',status:'processing',pages:15,preview:[demo('Processing. Preview not ready yet.')]},
 {id:'d4',title:'Fee Schedule (demo)',category:'Finance',department:'Finance',type:'xlsx',uploaded:'2026-03-01',status:'failed',pages:6,preview:[demo('Processing failed. Re-upload to retry.')]},
]
export const sources:Record<string,Source>={
 att:{n:1,docId:'d1',docTitle:'Student Handbook (demo)',page:2,quote:'Placeholder text about attendance expectations; real thresholds will come from official documents.'},
 exam:{n:1,docId:'d2',docTitle:'Examination Rules (demo)',page:2,quote:'Placeholder re-evaluation procedure outline.'},
}
export const conversations:Conversation[]=[
 {id:'c1',title:'Attendance requirements'},{id:'c2',title:'Re-evaluation process'},{id:'c3',title:'Hostel check-in'}]
export const history:Record<string,Message[]>={
 c1:[{id:'m1',role:'user',content:'What are the attendance requirements?'},
  {id:'m2',role:'assistant',content:'### Attendance (demo answer)\nThis is mock content. The handbook describes a minimum attendance requirement [1] and how absences are recorded.\n\n- Exact percentages appear here once real documents are added\n- Medical and duty leave rules would be cited from the source',sources:[sources.att]}],
 c2:[],c3:[]}
export const cannedReply=(p:string)=>{
 const exam=/exam|re-?eval|result/i.test(p)
 return {content:exam
  ?'### Re-evaluation (demo answer)\nThis is a **mock response**, not university policy. A re-evaluation process would be described in the examination rules [1].\n\n1. Find the application window in the source\n2. Check the fee and deadline\n3. Submit through the official portal\n\n```text\nDemo output only\n```'
  :'### Demo answer\nThis is a **mock response**, not official LPU information. A real answer would be grounded in documents from the knowledge base and cite them [1].\n\n- Attendance rules would cite the handbook\n- Exam questions would cite the examination rules',
  sources:[exam?sources.exam:sources.att]}
}
