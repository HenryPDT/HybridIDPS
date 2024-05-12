const WebSocket = require('ws');

    class WebSocketClient {
        constructor(url) {
            this.url = url;
            this.socket = new WebSocket(url);
    
            this.socket.on('open', () => {
                console.log('WebSocket connection established.');
            });
    
            this.socket.on('message', (data) => {
                const message = JSON.parse(data);
    
                console.log('Message received from server:', message);
                if (message.action === 'checkRegistration') {
                    this.send({ action: 'register', username: 'example_user', password: 'example_password', email: 'example@example.com' });
                }
                
                if (message.action === 'registrationSuccess') {
                    this.send({ action: 'login', username: 'example_user', password: 'example_password'});
                }

                

                if (message.action === 'viewFeedAndUser') {
                    this.send({ action: 'getPostList'});
                }

                // this.send({action: 'searchPosts', search: 'SELECT FROM WHERE JOIN'})

                let PostID;
    
                if (message.action === 'postList') {
                    let postList = message.posts;
                    postList = postList.filter((post) => (post.username === "Anthony Albonese" && post.postTitle === 'Fixing Infastructure'))
                    PostID = postList[0].postID;
                    this.send({ action: 'addComment', postID: PostID, comment: 'SELECT FROM WHERE JOIN'});
                }



                // this.send({action: 'reportUserByUsername', username: 'JohnSmith123'})
    
    
    
            });
    
            this.socket.on('close', () => {
                console.log('WebSocket connection closed.');
            });
    
            this.socket.on('error', (error) => {
                console.error('WebSocket error:', error);
            });
        }
    
        send(data) {
            this.socket.send(JSON.stringify(data));
            console.log('Message sent to server:', data);
        }
    }
    
    const client = new WebSocketClient('ws://localhost:8100'); // Replace with your WebSocket server address