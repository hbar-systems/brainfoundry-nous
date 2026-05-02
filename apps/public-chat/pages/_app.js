export default function App({ Component, pageProps }) {
  return (
    <>
      <style jsx global>{`
        html, body { margin: 0; padding: 0; background: #0e0c0b; }
      `}</style>
      <Component {...pageProps} />
    </>
  )
}
